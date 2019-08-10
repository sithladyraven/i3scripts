#!/usr/bin/env python3
#
# github.com/justbuchanan/i3scripts
#
# This script listens for i3 events and updates workspace names to show icons
# for running programs.  It contains icons for a few programs, but more can
# easily be added by editing the WINDOW_ICONS list below.
#
# It also re-numbers workspaces in ascending order with one skipped number
# between monitors (leaving a gap for a new workspace to be created). By
# default, i3 workspace numbers are sticky, so they quickly get out of order.
#
# Dependencies
# * xorg-xprop  - install through system package manager
# * i3ipc       - install with pip
# * fontawesome - install with pip
#
# Installation:
# * Download this repo and place it in ~/.config/i3/ (or anywhere you want)
# * Add "exec_always ~/.config/i3/i3scripts/autoname_workspaces.py &" to your i3 config
# * Restart i3: $ i3-msg restart
#
# Configuration:
# The default i3 config's keybindings reference workspaces by name, which is an
# issue when using this script because the "names" are constantly changing to
# include window icons.  Instead, you'll need to change the keybindings to
# reference workspaces by number.  Change lines like:
#   bindsym $mod+1 workspace 1
# To:
#   bindsym $mod+1 workspace number 1

import argparse
import i3ipc
import logging
import signal
import sys
import fontawesome as fa

from util import *

# Add icons here for common programs you use.  The keys are the X window class
# (WM_CLASS) names (lower-cased) and the icons can be any text you want to
# display.
#
# Most of these are character codes for font awesome:
#   http://fortawesome.github.io/Font-Awesome/icons/
#
# If you're not sure what the WM_CLASS is for your application, you can use
# xprop (https://linux.die.net/man/1/xprop). Run `xprop | grep WM_CLASS`
# then click on the application you want to inspect.
WINDOW_ICONS = {
    'alacritty': fa.icons['terminal'],
    'atom': fa.icons['code'],
    'banshee': fa.icons['play'],
    'blender': fa.icons['cube'],
    'chromium': fa.icons['chrome'],
    'cura': fa.icons['cube'],
    'darktable': fa.icons['image'],
    'discord': fa.icons['comment'],
    'eclipse': fa.icons['code'],
    'emacs': fa.icons['code'],
    'eog': fa.icons['image'],
    'evince': fa.icons['file-pdf'],
    'evolution': fa.icons['envelope'],
    'feh': fa.icons['image'],
    'file-roller': fa.icons['compress'],
    'filezilla': fa.icons['server'],
    'firefox': fa.icons['firefox'],
    'firefox-esr': fa.icons['firefox'],
    'gimp-2.8': fa.icons['image'],
    'gnome-control-center': fa.icons['toggle-on'],
    'gnome-terminal-server': fa.icons['terminal'],
    'google-chrome': fa.icons['chrome'],
    'gpick': fa.icons['eye-dropper'],
    'imv': fa.icons['image'],
    'java': fa.icons['code'],
    'jetbrains-idea': fa.icons['code'],
    'jetbrains-studio': fa.icons['code'],
    'keepassxc': fa.icons['key'],
    'keybase': fa.icons['key'],
    'kicad': fa.icons['microchip'],
    'kitty': fa.icons['terminal'],
    'libreoffice': fa.icons['file-alt'],
    'lua5.1': fa.icons['moon'],
    'lutris': fa.icons['steam'],
    'mpv': fa.icons['tv'],
    'mupdf': fa.icons['file-pdf'],
    'mysql-workbench-bin': fa.icons['database'],
    'nautilus': fa.icons['copy'],
    'nemo': fa.icons['copy'],
    'openscad': fa.icons['cube'],
    'pavucontrol': fa.icons['volume-up'],
    'postman': fa.icons['space-shuttle'],
    'rhythmbox': fa.icons['play'],
    'robo3t': fa.icons['database'],
    'slack': fa.icons['slack'],
    'slic3r.pl': fa.icons['cube'],
    'spotify': fa.icons['spotify'],
    'steam': fa.icons['steam'],
    'subl': fa.icons['file-alt'],
    'subl3': fa.icons['file-alt'],
    'sublime_text': fa.icons['file-alt'],
    'telegram-desktop': fa.icons['comment'],
    'termite': fa.icons['terminal'],
    'thunar': fa.icons['copy'],
    'thunderbird': fa.icons['envelope'],
    'totem': fa.icons['play'],
    'urxvt': fa.icons['terminal'],
    'xfce4-terminal': fa.icons['terminal'],
    'xournal': fa.icons['file-alt'],
    'yelp': fa.icons['code'],
    'zenity': fa.icons['window-maximize'],
    'zoom': fa.icons['comment'],
}

WINDOW_NAMES = {
    'atop': fa.icons['server'],
    'bash': fa.icons['terminal'],
    'emacs': fa.icons['file-code'],
    'glances': fa.icons['server'],
    'gotop': fa.icons['server'],
    'htop': fa.icons['server'],
    'mutt': fa.icons['envelope-square'],
    'neomutt': fa.icons['envelope-square'],
    'nano': fa.icons['file-code'],
    'nnn': fa.icons['folder-open'],
    'nvim': fa.icons['file-code'],
    'ranger': fa.icons['folder-open'],
    'ssh': fa.icons['terminal'],
    'sudo': fa.icons['user-shield'],
    'top': fa.icons['server'],
    'vi': fa.icons['file-code'],
    'vifm': fa.icons['folder-open'],
    'vim': fa.icons['file-code'],
    'zsh': fa.icons['terminal']
}

# This icon is used for any application not in the list above
DEFAULT_ICON = '*'

# If true, only the first non-default icon will be shown
SINGLE_ICON_ONLY = False

# Global setting that determines whether workspaces will be automatically
# re-numbered in ascending order with a "gap" left on each monitor. This is
# overridden via command-line flag.
RENUMBER_WORKSPACES = True

# Attempt to use window name first to determine the icon to be used
CHECK_WINDOW_NAMES_FIRST = True

# Require window names to be exact match. If false window names must only
# start with the provided name
REQUIRE_EXACT_NAME_MATCH = False

def ensure_window_icons_lowercase():
    global WINDOW_ICONS
    WINDOW_ICONS = {name.lower(): icon for name, icon in WINDOW_ICONS.items()}
    global WINDOW_NAMES
    WINDOW_NAMES = {name.lower(): icon for name, icon in WINDOW_NAMES.items()}

def icon_for_name(window):
    names = xprop(window.window, 'WM_NAME')
    if names != None and len(names) > 0:
        for nam in names:
            nam = nam.lower()
            if REQUIRE_EXACT_NAME_MATCH:
                if nam in WINDOW_NAMES:
                    return WINDOW_NAMES[nam]
            else:
                for k,v in WINDOW_NAMES.items():
                    if nam.startswith(k):
                        return v
    logging.info(
        'No icon available for window with names: %s' % str(names))

def icon_for_class(window):
    classes = xprop(window.window, 'WM_CLASS')
    if classes != None and len(classes) > 0:
        for cls in classes:
            cls = cls.lower()  # case-insensitive matching
            if cls in WINDOW_ICONS:
                return WINDOW_ICONS[cls]
    logging.info(
        'No icon available for window with classes: %s' % str(classes))

def icon_for_window(window):
    class_icon = icon_for_class(window)
    name_icon = icon_for_name(window)

    if CHECK_WINDOW_NAMES_FIRST and name_icon != None:
        return name_icon

    if class_icon != None:
        return class_icon

    return DEFAULT_ICON


# renames all workspaces based on the windows present
# also renumbers them in ascending order, with one gap left between monitors
# for example: workspace numbering on two monitors: [1, 2, 3], [5, 6]
def rename_workspaces(i3, icon_list_format='default'):
    ws_infos = i3.get_workspaces()
    prev_output = None
    n = 1
    for ws_index, workspace in enumerate(i3.get_tree().workspaces()):
        ws_info = ws_infos[ws_index]

        name_parts = parse_workspace_name(workspace.name)
        icon_list = [icon_for_window(w) for w in workspace.leaves()]
        if SINGLE_ICON_ONLY:
            icon_list = next((icon for icon in icon_list if icon != DEFAULT_ICON), DEFAULT_ICON)
        new_icons = format_icon_list(icon_list, icon_list_format)

        # As we enumerate, leave one gap in workspace numbers between each monitor.
        # This leaves a space to insert a new one later.
        if ws_info.output != prev_output and prev_output != None:
            n += 1
        prev_output = ws_info.output

        # optionally renumber workspace
        new_num = n if RENUMBER_WORKSPACES else name_parts.num
        n += 1

        new_name = construct_workspace_name(
            NameParts(
                num=new_num, shortname=name_parts.shortname, icons=new_icons))
        if workspace.name == new_name:
            continue
        i3.command(
            'rename workspace "%s" to "%s"' % (workspace.name, new_name))


# Rename workspaces to just numbers and shortnames, removing the icons.
def on_exit(i3):
    for workspace in i3.get_tree().workspaces():
        name_parts = parse_workspace_name(workspace.name)
        new_name = construct_workspace_name(
            NameParts(
                num=name_parts.num, shortname=name_parts.shortname,
                icons=None))
        if workspace.name == new_name:
            continue
        i3.command(
            'rename workspace "%s" to "%s"' % (workspace.name, new_name))
    i3.main_quit()
    sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=
        "Rename workspaces dynamically to show icons for running programs.")
    parser.add_argument(
        '--norenumber_workspaces',
        action='store_true',
        default=False,
        help=
        "Disable automatic workspace re-numbering. By default, workspaces are automatically re-numbered in ascending order."
    )
    parser.add_argument(
        '--icon_list_format',
        type=str,
        default='default',
        help=
        "The formatting of the list of icons."
        "Accepted values:"
        "    - default: no formatting,"
        "    - mathematician: factorize with superscripts (e.g. aababa -> a⁴b²),"
        "    - chemist: factorize with subscripts (e.g. aababa -> a₄b₂)."
    )
    args = parser.parse_args()

    RENUMBER_WORKSPACES = not args.norenumber_workspaces

    logging.basicConfig(level=logging.INFO)

    ensure_window_icons_lowercase()

    i3 = i3ipc.Connection()

    # Exit gracefully when ctrl+c is pressed
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda signal, frame: on_exit(i3))

    rename_workspaces(i3, icon_list_format=args.icon_list_format)

    # Call rename_workspaces() for relevant window events
    def event_handler(i3, e):
        if e.change in ['new', 'close', 'move']:
            rename_workspaces(i3, icon_list_format=args.icon_list_format)

    i3.on('window', event_handler)
    i3.on('workspace::move', event_handler)
    i3.main()
