// StudyRoom Timer - top-bar indicator for the StudyRoom study app.
// It only READS ~/.local/share/ypt-study/timer.json (written by the app) and asks the app,
// over D-Bus (org.gtk.Actions), to pause/resume/stop/show. It never writes any files.
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const APP_ID = 'io.github.studyroom.Studyroom';
const APP_PATH = '/io/github/studyroom/Studyroom';
const TIMER_FILE = 'timer.json';

function pad(n) {
    return String(n).padStart(2, '0');
}

function clock(secs) {
    secs = Math.max(0, Math.floor(secs));
    return `${pad(Math.floor(secs / 3600))}:${pad(Math.floor(secs % 3600 / 60))}:${pad(secs % 60)}`;
}

function safeColor(c) {
    return /^#[0-9a-fA-F]{6}$/.test(c ?? '') ? c : '#888888';
}

const Indicator = GObject.registerClass(
class StudyRoomIndicator extends PanelMenu.Button {
    _init(dataDir) {
        super._init(0.5, 'StudyRoom Timer');
        this._dir = dataDir;
        this._state = null;

        const box = new St.BoxLayout({style_class: 'studyroom-box', y_align: Clutter.ActorAlign.CENTER});
        this._dot = new St.Widget({style_class: 'studyroom-dot', y_align: Clutter.ActorAlign.CENTER});
        this._pauseIcon = new St.Icon({
            icon_name: 'media-playback-pause-symbolic', style_class: 'system-status-icon studyroom-pause',
            visible: false,
        });
        this._label = new St.Label({text: '', style_class: 'studyroom-label', y_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._dot);
        box.add_child(this._pauseIcon);
        box.add_child(this._label);
        this.add_child(box);

        this._header = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this._header);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._pauseItem = this.menu.addAction('Pause', () => this._activate('toggle-pause'));
        this.menu.addAction('Stop & save', () => this._activate('stop'));
        this.menu.addAction('Open StudyRoom', () => this._activate('show'));

        const file = this._dir.get_child(TIMER_FILE);
        this._path = file.get_path();
        try {
            this._monitor = this._dir.monitor_directory(Gio.FileMonitorFlags.NONE, null);
            this._monitorId = this._monitor.connect('changed', (_m, f, other) => {
                if (f?.get_basename() === TIMER_FILE || other?.get_basename() === TIMER_FILE)
                    this._reload();
            });
        } catch (e) {
            this._monitor = null;
        }
        this._reload();
        this._tickId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._tickCount = (this._tickCount ?? 0) + 1;
            if (this._tickCount % 10 === 0)
                this._reload();     // safety net in case a file event was missed
            else
                this._render();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _reload() {
        let state = null;
        try {
            const [ok, bytes] = GLib.file_get_contents(this._path);
            if (ok) {
                const s = JSON.parse(new TextDecoder().decode(bytes));
                if (s && s.active)
                    state = s;
            }
        } catch (e) {
            state = null;
        }
        this._state = state;
        this._render();
    }

    _elapsed() {
        const s = this._state;
        let e = Number(s.accum) || 0;
        if (s.run_start)
            e += Date.now() / 1000 - Number(s.run_start);
        if (s.mode === 'down' && s.target)
            e = Math.min(e, Number(s.target));
        return e;
    }

    _render() {
        const s = this._state;
        this.visible = !!s;
        if (!s)
            return;
        const paused = !s.run_start;
        const e = this._elapsed();
        const shown = s.mode === 'down' && s.target ? Number(s.target) - e : e;
        const name = String(s.subject ?? '').slice(0, 24);
        this._dot.set_style(`background-color: ${safeColor(s.color)};`);
        this._dot.visible = !paused;
        this._pauseIcon.visible = paused;
        this._label.text = `${name}  ${clock(shown)}`;
        this._label.opacity = paused ? 160 : 255;
        const mode = s.mode === 'down' ? `Countdown · ${Math.round(Number(s.target) / 60)} min` : 'Counting up';
        this._header.label.text = `${name} · ${mode}${paused ? ' · paused' : ''}`;
        this._pauseItem.label.text = paused ? 'Resume' : 'Pause';
    }

    _activate(action) {
        Gio.DBus.session.call(
            APP_ID, APP_PATH, 'org.gtk.Actions', 'Activate',
            new GLib.Variant('(sava{sv})', [action, [], {}]),
            null, Gio.DBusCallFlags.NONE, -1, null,
            (conn, res) => {
                try {
                    conn.call_finish(res);
                } catch (e) {
                    // App not running: launch it instead.
                    const info = Gio.DesktopAppInfo.new(`${APP_ID}.desktop`);
                    try {
                        info?.launch([], null);
                    } catch (e2) {
                        console.warn(`StudyRoom Timer: could not launch app: ${e2.message}`);
                    }
                }
            });
    }

    destroy() {
        if (this._tickId) {
            GLib.source_remove(this._tickId);
            this._tickId = 0;
        }
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        super.destroy();
    }
});

export default class StudyRoomTimerExtension extends Extension {
    enable() {
        const dir = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_data_dir(), 'ypt-study']));
        this._indicator = new Indicator(dir);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
