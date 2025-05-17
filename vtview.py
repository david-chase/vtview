import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from functools import partial
import configparser
import re
import webbrowser
import stat
import time
import csv

def scrub_filename(filename: str) -> str:
    import string

    # Step 1: Parse root and tags section
    if " #" not in filename:
        return filename  # No tag section present

    base, ext = os.path.splitext(filename)
    root_split = base.split(" #", 1)
    root = root_split[0]
    tag_section = root_split[1]

    # Step 2: Clean up the tags section
    # Remove all whitespace and punctuation (except #)
    tag_section = ''.join(c for c in tag_section if c not in string.whitespace + string.punctuation or c == '#')

    # Step 3: Parse individual tags
    tags = []
    current_tag = ''
    in_tag = False
    for c in tag_section:
        if c == '#':
            if in_tag and current_tag:
                tags.append(f"#{current_tag}")
            current_tag = ''
            in_tag = True
        elif in_tag:
            current_tag += c

    if in_tag and current_tag:
        tags.append(f"#{current_tag}")

    # Step 4: Deduplicate and handle priority tag
    priority_tags = {"#1", "#2", "#3", "#4", "#5"}
    last_priority = None
    filtered_tags = []
    seen = set()

    for tag in reversed(tags):
        if tag in priority_tags and not last_priority:
            last_priority = tag
        elif tag not in priority_tags and tag not in seen:
            seen.add(tag)
            filtered_tags.append(tag)

    if last_priority:
        filtered_tags.append(last_priority)

    # Step 5: Sort tags alphabetically
    filtered_tags = sorted(filtered_tags, key=lambda t: (t not in priority_tags, t))

    # Step 6: Reassemble filename
    tag_str = ''.join(filtered_tags)
    return f"{root} {tag_str}{ext}" if tag_str else f"{root}{ext}"

class ImageBrowserApp:
    # For one or more files, check if there is a model specified in the filename that
    # corresponds to a model name in the database.  If yes, merge in the tags from
    # the database into the filename, then scrub it.
    def pull_tags_from_database(self, event=None):

        
        return

    # Read in the Models CSV
    def load_models_database(self):
        models = []
        try:
            datafiles_dir = os.path.expandvars("%DataFiles%")
            csv_path = os.path.join(datafiles_dir, "models.csv")
            if not os.path.exists(csv_path):
                if self.debug_mode:
                    print(f"Models database not found: {csv_path}")
                return models

            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if all(k in row for k in ("name", "tags", "url")):
                        models.append({
                            "name": row["name"].strip(),
                            "tags": row["tags"].strip(),
                            "url": row["url"].strip()
                        })
        except Exception as e:
            messagebox.showerror("Models DB Load Error", f"Failed to load models.csv:\n{e}")
        return models

    # Called when you press the move up a folder ".." button
    def go_up_one_folder(self):
        parent = os.path.dirname(self.current_folder)
        if parent and os.path.isdir(parent) and parent != self.current_folder:
            self.current_folder = parent
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()

    # Helps detect folders that are hidden or system so we can ignore them
    def is_hidden_or_system(self, path):
        try:
            if os.name == 'nt':
                attrs = os.stat(path).st_file_attributes
                return bool(attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))
            else:
                return os.path.basename(path).startswith('.')
        except AttributeError:
            # st_file_attributes may not exist on some systems
            return os.path.basename(path).startswith('.')

    # Build the menu bar dynamically from the shortcuts in our ini file
    def build_menu_bar(self):
        import tkinter as tk

        # Initialize menu bar
        menubar = tk.Menu(self.root, bg=self.colors["background"], fg=self.colors["foreground"])

        # Step 1: Collect all shortcuts grouped by submenu
        menus = {}
        for func_name, shortcut in self.shortcut_keys.items():
            submenu = shortcut.get("menu", "Other")
            if submenu not in menus:
                menus[submenu] = []
            menus[submenu].append((func_name, shortcut))

        # Step 2: Determine desired menu order from ini (if defined)
        menu_order_str = self.config.get("Settings", "MenuOrder", fallback="")
        ordered_names = [m.strip() for m in menu_order_str.split(",") if m.strip()]

        # Step 3: Append unordered submenus alphabetically
        all_submenus = list(menus.keys())
        remaining = sorted([m for m in all_submenus if m not in ordered_names])
        full_order = ordered_names + remaining

        # Step 4: Function mapping
        keymap = {
            "delete_file": self.prompt_delete_selected_files,
            "refresh_folder": self.refresh_folder,
            "rename_file": self.prompt_rename_selected_file,
            "fullscreen_view": self.show_fullscreen_image,
            "move_file": self.move_files_to_folder,
            "copy_file": self.copy_files_to_folder,
            "rewrite_file": self.rewrite_file_names,
            "toss_to_model": self.toss_to_model_folder,
            "add_tag": self.add_custom_tag,
            "make_index": self.make_index_file,
            "remove_tag": self.remove_custom_tag,
            "open_help": self.open_help_url
        }
        for i in range(1, 6):
            keymap[f"alt_tag_{i}"] = lambda idx=i: self._tag_shortcut_handler(idx)

        # Step 5: Build menus with two-column layout using 'label' and 'accelerator'
        for menu_name in full_order:
            submenu_items = menus.get(menu_name, [])
            menu = tk.Menu(menubar, tearoff=0, bg=self.colors["background"], fg=self.colors["foreground"])

            for func_name, shortcut in submenu_items:
                label = shortcut.get("name", func_name)
                key_display = shortcut.get("key", "")
                handler = keymap.get(func_name)

                if handler:
                    menu.add_command(
                        label=label,
                        accelerator=key_display,
                        command=lambda h=handler: h() if callable(h) else None
                    )

            menubar.add_cascade(label=menu_name, menu=menu)

        self.root.config(menu=menubar)

    # I've selected a folder from the favourites drop-down.  Switch to it.
    def change_to_favorite_folder(self, event=None):
        selected = self.fav_folder_var.get()
        if selected and os.path.isdir(selected):
            self.current_folder = selected
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()

    # I've clicked the toggle to change sort order
    def toggle_sort_direction(self):
        self.sort_ascending = not self.sort_ascending
        self.load_images()

    # I'm sorting ascending
    def set_sort_ascending(self):
        self.sort_ascending = True
        self.load_images()

    # I'm sorting descending
    def set_sort_descending(self):
        self.sort_ascending = False
        self.load_images()

    # I want to sort by something other than filename
    def sort_key_factory(self, method):
        def sort_key(filename):
            path = os.path.join(self.current_folder, filename)
            try:
                if method == "Size":
                    return os.path.getsize(path)
                elif method == "Created":
                    return os.path.getctime(path)
                elif method == "Modified":
                    return os.path.getmtime(path)
                else:
                    return filename.lower()
            except:
                return 0
        return sort_key

    # If I hover over a file in the file list for over a second
    def on_listbox_motion(self, event):
        index = self.listbox.nearest(event.y)

        # If same index as before, do nothing
        if self.tooltip_index == index:
            return

        self.hide_tooltip()  # Cancel previous tooltip if any
        self.tooltip_index = index

        # Schedule new tooltip
        self.tooltip_after_id = self.root.after(1000, lambda: self.show_tooltip(event, index))

    # Show a tooltip with the full filename
    def show_tooltip(self, event, index):
        if self.tooltip_window:
            return  # Already showing

        try:
            text = self.listbox.get(index)
        except tk.TclError:
            return

        x = self.listbox.winfo_rootx() + event.x + 10
        y = self.listbox.winfo_rooty() + event.y + 10

        self.tooltip_window = tw = tk.Toplevel(self.listbox)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="black")

        label = tk.Label(tw, text=text, bg="black", fg="white", font=("Arial", 10), padx=5, pady=2)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip_after_id:
            self.root.after_cancel(self.tooltip_after_id)
            self.tooltip_after_id = None

        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

        self.tooltip_index = None

    def ask_tag_to_remove(self):
        top = tk.Toplevel(self.root)
        top.title("Remove Tag")
        top.geometry("300x120")
        top.grab_set()
        top.resizable(False, False)
        top.configure(bg=self.colors["background"])

        tk.Label(top, text="Enter tag to remove (e.g. #example):", bg=self.colors["background"], fg=self.colors["foreground"]).pack(pady=(10, 0))

        var = tk.StringVar()
        entry = tk.Entry(top, textvariable=var, bg=self.colors["entry_background"], fg=self.colors["entry_foreground"], insertbackground=self.colors["foreground"])
        entry.pack(padx=10, pady=10, fill=tk.X)
        entry.focus()

        def on_enter(event):
            top.destroy()

        def on_escape(event):
            var.set("")
            top.destroy()

        entry.bind("<Return>", on_enter)
        entry.bind("<Escape>", on_escape)

        top.wait_window()
        return var.get().strip()

    def ask_tag_with_autocomplete(self):
        top = tk.Toplevel(self.root)
        top.title("Add Tag")
        top.geometry("300x200")
        top.grab_set()
        top.resizable(False, False)
        top.configure(bg=self.colors["background"])

        tk.Label(top, text="Enter tag:", bg=self.colors["background"], fg=self.colors["foreground"]).pack(pady=(10, 0))

        var = tk.StringVar()
        entry = tk.Entry(top, textvariable=var, bg=self.colors["entry_background"], fg=self.colors["entry_foreground"], insertbackground=self.colors["foreground"])
        entry.pack(padx=10, pady=(5, 10), fill=tk.X)
        entry.focus()

        listbox = tk.Listbox(top, height=5, bg=self.colors["list_background"], fg=self.colors["foreground"], selectbackground=self.colors["highlight"])
        listbox.pack(padx=10, pady=(0, 10), fill=tk.BOTH, expand=True)

        favorites = sorted([t.strip().lower() for t in self.config.get("Tags", "favorites", fallback="").split(",") if t.strip()])

        def on_escape(event):
            var.set("")
            top.destroy()

        def update_suggestions(*args):
            typed = var.get().lower()
            filtered = [tag for tag in favorites if tag.startswith(typed)] if typed else favorites
            listbox.delete(0, tk.END)
            for tag in filtered:
                listbox.insert(tk.END, tag)

        def on_select():
            selection = listbox.curselection()
            if selection:
                var.set(listbox.get(selection[0]))
                top.after(100, top.destroy)

        def on_enter_entry(event):
            top.destroy()

        def on_down_arrow(event):
            if listbox.size() > 0:
                listbox.focus_set()
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(0)
                listbox.activate(0)
            return "break"

        def on_listbox_enter(event):
            on_select()
            return "break"

        var.trace_add("write", update_suggestions)
        entry.bind("<Return>", on_enter_entry)
        entry.bind("<Down>", on_down_arrow)
        entry.bind("<Escape>", on_escape)

        listbox.bind("<Return>", on_listbox_enter)
        listbox.bind("<Double-Button-1>", lambda e: on_select())
        listbox.bind("<Escape>", on_escape)

        update_suggestions()

        top.wait_window()
        return var.get().strip()

    def open_help_url(self, event=None):
        webbrowser.open("https://github.com/david-chase/vtview/blob/main/README.md")    
    
    def show_status_dialog(self, title, filenames):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x120")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(bg=self.colors["background"])

        label = tk.Label(dialog, text="", bg=self.colors["background"], fg=self.colors["foreground"], anchor="w")
        label.pack(fill=tk.X, padx=10, pady=(15, 5))

        progress = ttk.Progressbar(dialog, orient="horizontal", length=360, mode="determinate")
        progress.pack(pady=(0, 15))
        progress["maximum"] = len(filenames)

        return dialog, label, progress
    
    def make_index_file(self, event=None):

        selection = self.listbox.curselection()
        if not selection:
            return

        for i in selection:
            filename = self.listbox.get(i)

            # Pull the escape hatch if this is a folder
            file_path = os.path.join(self.current_folder, filename)
            if os.path.isdir(file_path):
                return
            
            base, ext = os.path.splitext(filename)

            # Check if "-" exists
            if "-" not in base:
                continue

            model_part, rest = base.split("-", 1)
            if " " in model_part:
                continue  # model name must not contain whitespace

            # Extract tags (starting from first "#")
            tag_match = re.search(r"(#.+)", base)
            tags = tag_match.group(1).strip() if tag_match else ""

            # Extract root name (everything after "-" and before tags)
            root_match = re.split(r"\s+#", rest, maxsplit=1)
            root_name = root_match[0].strip()

            # Construct new index filename
            new_filename = f"{model_part}-index {tags}{ext}"
            src_path = os.path.join(self.current_folder, filename)
            dst_path = os.path.join(self.current_folder, new_filename)

            if not os.path.exists(dst_path):
                try:
                    shutil.copy2(src_path, dst_path)
                except Exception as e:
                    messagebox.showerror("Index Copy Failed", f"Failed to create index file for {filename}:\n{e}")
            
            self.load_images()

    def remove_custom_tag(self, event=None):

        selection = self.listbox.curselection()
        if not selection:
            return

        tag = self.ask_tag_to_remove()
        if not tag:
            return

        tag = tag.strip()
        if not tag.startswith("#"):
            tag = f"#{tag}"

        filenames = [self.listbox.get(i) for i in selection]
        updated_filenames = []
        dialog, label, progress = self.show_status_dialog("Removing Tag", filenames)

        for i, filename in enumerate(filenames):
            # Pull the escape hatch if this is a folder
            file_path = os.path.join(self.current_folder, filename)
            if os.path.isdir(file_path):
                return
        
            label.config(text=filename)
            dialog.update_idletasks()

            base, ext = os.path.splitext(filename)
            modified = re.sub(re.escape(tag), "", base, flags=re.IGNORECASE)
            new_filename = scrub_filename(f"{modified}{ext}")

            if new_filename == filename:
                continue

            src = os.path.join(self.current_folder, filename)
            dst = os.path.join(self.current_folder, new_filename)

            try:
                os.rename(src, dst)
                updated_filenames.append(new_filename)
            except Exception as e:
                messagebox.showerror("Rename Failed", f"Could not remove tag from {filename}:\n{e}")

            progress["value"] = i + 1

        dialog.destroy()

        if updated_filenames:
            self.load_images()
            filenames = self.listbox.get(0, tk.END)
            self.listbox.selection_clear(0, tk.END)
            for fname in updated_filenames:
                try:
                    idx = filenames.index(fname)
                    self.listbox.selection_set(idx)
                    self.listbox.activate(idx)
                    self.listbox.see(idx)
                except ValueError:
                    continue
            self.listbox.focus_set()
            self.listbox.event_generate("<<ListboxSelect>>")


    def add_custom_tag(self, event=None):
        # Debugging
        # messagebox.showinfo("Debug", "Break")

        selection = self.listbox.curselection()
        if not selection:
            return

        # Prompt for the tag to add
        tag = self.ask_tag_with_autocomplete()
        if not tag:
            return

        # If the tag doesn't have a # on it, add one
        tag = tag.strip()
        if not tag.startswith("#"):
            tag = f"#{tag}"

        filenames = [self.listbox.get(i) for i in selection]
        updated_filenames = []
        dialog, label, progress = self.show_status_dialog("Adding Tag", filenames)

        # This loop does all the processing
        for i, filename in enumerate(filenames):
            # Pull the escape hatch if this is a folder
            file_path = os.path.join(self.current_folder, filename)
            if os.path.isdir(file_path):
                continue

            label.config(text=filename)
            dialog.update_idletasks()

            base, ext = os.path.splitext(filename)
            new_filename = scrub_filename(f"{base}{tag}{ext}")
            if new_filename == filename:
                continue

            src = os.path.join(self.current_folder, filename)
            dst = os.path.join(self.current_folder, new_filename)

            try:
                os.rename(src, dst)
                updated_filenames.append(new_filename)
            except Exception as e:
                messagebox.showerror("Rename Failed", f"Could not add tag to {filename}:\n{e}")

            progress["value"] = i + 1

        dialog.destroy()

        if updated_filenames:
            self.load_images()
            filenames = self.listbox.get(0, tk.END)
            self.listbox.selection_clear(0, tk.END)
            for fname in updated_filenames:
                try:
                    idx = filenames.index(fname)
                    self.listbox.selection_set(idx)
                    self.listbox.activate(idx)
                    self.listbox.see(idx)
                except ValueError:
                    continue
            self.listbox.focus_set()
            self.listbox.event_generate("<<ListboxSelect>>")

    # Handle the Alt-1 to Alt-5 keys
    def _tag_shortcut_handler(self, tag_number, event=None):
        tag = f"#{tag_number}"
        selected_indices = self.listbox.curselection()
        updated_filenames = []

        for index in selected_indices:
            filename = self.listbox.get(index)
            full_path = os.path.join(self.current_folder, filename)
            if os.path.isdir(full_path):
                continue

            new_name = self.tag_file_with_priority(tag, filename)
            if new_name:
                updated_filenames.append(new_name)

        if updated_filenames:
            self.load_images()
            filenames = self.listbox.get(0, tk.END)
            self.listbox.selection_clear(0, tk.END)
            for fname in updated_filenames:
                try:
                    idx = filenames.index(fname)
                    self.listbox.selection_set(idx)
                    self.listbox.activate(idx)
                    self.listbox.see(idx)
                except ValueError:
                    continue
            self.listbox.focus_set()
            self.listbox.event_generate("<<ListboxSelect>>")

    #---------------------------------------------------------
    #  Our main init section
    #---------------------------------------------------------
    def __init__(self, root):
        self.root = root
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.script_dir, "vtview.ini")
        self.config = self.load_config()

        # Read in whether we want to render folders in the file list
        self.show_folders = self.config.get("Settings", "ShowFolders", fallback="false").lower() == "true"

        # Read in whether DebugMode = true
        self.debug_mode = self.config.get("Settings", "DebugMode", fallback="false").lower() == "true"

        # Read in the theme data
        self.colors = self.get_colors()

        # Read in the list of "image" types 
        self.supported_formats = self.get_supported_extensions()

        # Keyboard bindings (which also inform menu bar)
        self.shortcut_keys = self.get_shortcuts()

        # Default folder
        self.default_folder = self.config.get("Settings", "default_folder", fallback=os.getcwd())

        # Current folder
        self.current_folder = self.default_folder
        
        # Load the models database from %DataFiles%\models.csv
        self.models_db = self.load_models_database()

        # Set the window title
        self.root.title(f"VtView - {self.current_folder}")
        self.root.configure(bg=self.colors["background"])

        # Launch the menu bar
        self.build_menu_bar()

        # The search bar
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.update_file_list)

        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.colors["background"])
        self.paned.pack(fill=tk.BOTH, expand=True)

        screen_width = self.root.winfo_screenwidth()
        list_width_fraction = float(self.config.get("Settings", "file_list_width", fallback="0.33"))
        left_frame_width = int(screen_width * list_width_fraction)

        self.left_frame = tk.Frame(self.paned, width=left_frame_width, bg=self.colors["background"])
        self.left_frame.pack_propagate(False)
        self.paned.add(self.left_frame, minsize=200)

        self.search_entry = tk.Entry(
            self.left_frame,
            textvariable=self.search_var,
            bg=self.colors["entry_background"],
            fg=self.colors["entry_foreground"],
            insertbackground=self.colors["foreground"]
        )
        self.search_entry.pack(padx=10, pady=(10, 0), fill=tk.X)

        folder_sort_frame = tk.Frame(self.left_frame, bg=self.colors["background"])
        folder_sort_frame.pack(padx=10, pady=(5, 0), fill=tk.X)

        # Select folder button
        self.select_button = tk.Button(
            folder_sort_frame,
            text="Select folder",
            width=12,
            bg=self.colors["button_background"],
            fg=self.colors["button_foreground"],
            activebackground=self.colors["highlight"],
            command=self.select_folder
        )
        self.select_button.pack(side=tk.LEFT)

        # Move up a folder button ".."
        self.up_button = tk.Button(
            folder_sort_frame,
            text="..",
            width=3,
            bg=self.colors["button_background"],
            fg=self.colors["button_foreground"],
            activebackground=self.colors["highlight"],
            command=self.go_up_one_folder
        )
        self.up_button.pack(side=tk.LEFT, padx=(5, 5))

        # Sort by label
        tk.Label(
            folder_sort_frame,
            text="Sort by:",
            bg=self.colors["background"],
            fg=self.colors["foreground"]
        ).pack(side=tk.LEFT, padx=(10, 2))

        # Sort by drop-down
        self.sort_var = tk.StringVar(value="Name")
        self.sort_dropdown = ttk.Combobox(
            folder_sort_frame,
            textvariable=self.sort_var,
            values=["Name", "Size", "Created", "Modified"],
            state="readonly",
            width=10
        )
        self.sort_dropdown.pack(side=tk.LEFT)

        self.sort_ascending = True  # default sort direction

        # Sort order toggle button
        self.sort_toggle_button = tk.Button(
            folder_sort_frame,
            text="↑/↓",
            width=3,
            command=self.toggle_sort_direction
        )
        self.sort_toggle_button.pack(side=tk.LEFT, padx=2)

        # Favourites label
        tk.Label(
            folder_sort_frame,
            text="Favourites:",
            bg=self.colors["background"],
            fg=self.colors["foreground"]
        ).pack(side=tk.LEFT, padx=(10, 2))

        # Favourites drop-down
        self.fav_folders = [f.strip() for f in self.config.get("Settings", "FavouriteFolders", fallback="").split(",") if f.strip()]
        self.fav_folder_var = tk.StringVar()
        self.fav_folder_dropdown = ttk.Combobox(
            folder_sort_frame,
            textvariable=self.fav_folder_var,
            values=self.fav_folders,
            state="readonly",
            width=20
        )
        self.fav_folder_dropdown.pack(side=tk.LEFT, padx=(10, 0))
        self.fav_folder_dropdown.bind("<<ComboboxSelected>>", self.change_to_favorite_folder)

        self.sort_dropdown.bind("<<ComboboxSelected>>", lambda e: self.load_images())

        # Create the file list box
        listbox_frame = tk.Frame(self.left_frame, bg=self.colors["foreground"], bd=1, relief="solid")
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=(0,0), pady=(10,0))

        # Add the scrollbar to the file list box
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Fancy up the scrollbar
        style = ttk.Style()
        style.theme_use("clam")  # looks good in dark mode
        style.configure("Vertical.TScrollbar",
            background=self.colors["button_background"],
            troughcolor=self.colors["background"],
            bordercolor=self.colors["background"],
            arrowcolor=self.colors["foreground"]
        )

        # Set properties and style for file list box
        self.listbox = tk.Listbox(
            listbox_frame,
            selectmode=tk.EXTENDED,
            bg=self.colors["list_background"],
            fg=self.colors["foreground"],
            selectbackground=self.colors["highlight"],
            highlightthickness=0,
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set,
            activestyle="none"
        )

        # More file list box junk
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.show_selected_image)
        self.listbox.bind("<Motion>", self.on_listbox_motion)
        self.listbox.bind("<Leave>", self.hide_tooltip)

        # Status message at bottom
        self.status_label = tk.Label(
            self.left_frame,
            text="",
            anchor="w",
            bg=self.colors["background"],
            fg=self.colors["foreground"],
            font=("Arial", 9)
        )
        self.status_label.pack(fill=tk.X, padx=0, pady=(2, 5))

        # Tooltips if I hover over a filename
        self.tooltip_window = None
        self.tooltip_after_id = None
        self.tooltip_index = None

        # This is the "canvas" right pane
        self.right_frame = tk.Frame(self.paned, bg=self.colors["background"])
        self.paned.add(self.right_frame)

        self.canvas = tk.Canvas(self.right_frame, bg=self.colors["canvas_background"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=(0,0), pady=(10,5))

        # Load the list of images
        self.load_images()
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        self.current_image = None
        self.current_image_path = None
        self.fullscreen_window = None
        self.all_files = []

        # Bind keys
        keymap = {
            "delete_file": self.prompt_delete_selected_files,
            "refresh_folder": self.refresh_folder,
            "rename_file": self.prompt_rename_selected_file,
            "fullscreen_view": self.show_fullscreen_image,
            "move_file": self.move_files_to_folder,
            "copy_file": self.copy_files_to_folder,
            "rewrite_file": self.rewrite_file_names,
            "toss_to_model": self.toss_to_model_folder,
            "add_tag": self.add_custom_tag,
            "make_index": self.make_index_file,
            "remove_tag": self.remove_custom_tag,
            "open_help": self.open_help_url,
            "tag_from_db": self.pull_tags_from_database
        }

        for keyname, handler in keymap.items():
            shortcut = self.shortcut_keys.get(keyname)
            if shortcut:
                binding = self.normalize_binding(shortcut["key"])

                def wrapped_handler(event, h=handler):
                    h()
                    return "break"

                self.root.bind_all(binding, wrapped_handler)

        # Map the Alt-1 to Alt-5 keys
        for i in range(1, 6):
            shortcut = self.shortcut_keys.get(f"alt_tag_{i}")
            key_string = shortcut["key"] if isinstance(shortcut, dict) else shortcut or f"Alt-{i}"
            binding = self.normalize_binding(key_string)
            self.root.bind_all(binding, partial(self._tag_shortcut_handler, i))


        # Set the focus on file list and select first item on app load
        if self.listbox.size() > 0:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.listbox.event_generate("<<ListboxSelect>>")
        self.listbox.focus_set()

    def normalize_binding(self, key_str):
        key_str = key_str.strip()

        # Alt keys
        if key_str.lower().startswith("alt-") and key_str[4:].isdigit():
            return f"<Alt-Key-{key_str[4:]}>"

        # Special keys, proper casing
        special_keys = {
            "home": "Home",
            "end": "End",
            "delete": "Delete",
            "return": "Return",
            "f1": "F1",
            "f2": "F2",
            "f5": "F5",
        }

        normalized = special_keys.get(key_str.lower(), key_str)
        return f"<{normalized}>"

    # Add a rating tag to one or more images
    def tag_file_with_priority(self, tag_value, filename):
        base, ext = os.path.splitext(filename)
        modified_filename = f"{base} #{tag_value}{ext}"
        cleaned_filename = scrub_filename(modified_filename)

        if cleaned_filename == filename:
            return

        old_path = os.path.join(self.current_folder, filename)
        new_path = os.path.join(self.current_folder, cleaned_filename)

        if os.path.exists(new_path):
            messagebox.showerror("Rename Failed", f"{cleaned_filename} already exists.")
            return

        try:
            os.rename(old_path, new_path)
            return cleaned_filename
        except Exception as e:
            messagebox.showerror("Rename Failed", f"Failed to apply tag #{tag_value} to {filename}:\n{e}")
            return None

    def toss_to_model_folder(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        model_base_dir = self.config.get("Settings", "ModelBaseDir", fallback=None)
        video_base_dir = self.config.get("Settings", "VideoBaseDir", fallback=None)
        video_all_dir = self.config.get("Settings", "VideoAllDir", fallback=None)

        if not model_base_dir or not os.path.isdir(model_base_dir):
            messagebox.showwarning("Invalid Base Folder", "ModelBaseDir is not defined or does not exist.")
            return

        raw_video_exts = self.config.get("Settings", "videoextensions", fallback="")
        video_exts = tuple(
            ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}"
            for ext in raw_video_exts.split(",") if ext.strip()
        )

        filenames = [self.listbox.get(i) for i in selection]
        dialog, label, progress = self.show_status_dialog("Tossing to Model Folder", filenames)
        moved_files = 0

        for i, filename in enumerate(filenames):
            label.config(text=filename)
            dialog.update_idletasks()

            match = re.match(r"([^-\s]+)", filename)
            if not match:
                continue

            model_name = match.group(1)
            file_ext = os.path.splitext(filename)[1].lower()
            is_video = file_ext in video_exts

            model_folder = os.path.join(model_base_dir, model_name)
            model_folder_exists = os.path.isdir(model_folder)

            if is_video:
                if model_folder_exists and video_base_dir and os.path.isdir(video_base_dir):
                    target_dir = video_base_dir
                elif video_all_dir and os.path.isdir(video_all_dir):
                    target_dir = video_all_dir
                else:
                    continue  # skip if neither video base dir exists
            else:
                if not model_folder_exists:
                    continue
                target_dir = model_folder

            src = os.path.join(self.current_folder, filename)
            dest = os.path.join(target_dir, filename)

            try:
                shutil.move(src, dest)
                moved_files += 1
            except Exception as e:
                messagebox.showerror("Move Failed", f"Could not move {filename}:\n{e}")

            progress["value"] = i + 1

        dialog.destroy()

        if moved_files:
            self.load_images()

    # Read in the inifile
    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        return config

    # Read in the list of supproted file types, including ones defined as being for videos
    def get_supported_extensions(self):
        extensions = self.config.get("Settings", "extensions", fallback=".jpg,.jpeg,.gif,.webp,.png")
        video_extensions = self.config.get("Sections", "videoextensions", fallback=".mp4,.avi,.webm").lower()

        self.video_extensions = tuple(e.strip().lower() for e in video_extensions.split(",") if e.strip())
        return tuple(e.strip().lower() for e in extensions.split(",") if e.strip())

    # Read shortcuts and kep mappings from the ini file
    def get_shortcuts(self):
        shortcuts = {}
        if self.config.has_section("Shortcuts"):
            for func_name, line in self.config.items("Shortcuts"):
                parts = [p.strip() for p in line.split(",", 3)]
                if len(parts) >= 2:
                    shortcuts[func_name] = {
                        "key": parts[0],
                        "name": parts[1] if len(parts) > 1 else func_name,
                        "menu": parts[2] if len(parts) > 2 else "General"
                    }
        return shortcuts

    # Read in the theme from the ini file
    def get_colors(self):
        # Set default colours in case nothing is specified in the ini file
        default_colors = {
            "background": "#1e1e1e",
            "foreground": "#e0e0e0",
            "highlight": "#007acc",
            "button_background": "#2d2d2d",
            "button_foreground": "#ffffff",
            "entry_background": "#2a2a2a",
            "entry_foreground": "#ffffff",
            "list_background": "#1e1e1e",
            "list_background_alt": "#252525",
            "canvas_background": "#1e1e1e",
            "folder_foreground": "#007700",
            "invalid_foreground": "#888888"
        }
        if self.config.has_section("Colors"):
            for key in default_colors:
                default_colors[key] = self.config.get("Colors", key, fallback=default_colors[key])
        
            # Optional extensions
            default_colors["list_background"] = self.config.get("Colors", "list_background", fallback=default_colors["background"])
            default_colors["canvas_background"] = self.config.get("Colors", "canvas_background", fallback=default_colors["background"])        
            default_colors["invalid_foreground"] = self.config.get("Colors", "invalid_foreground", fallback=default_colors["invalid_foreground"])
            default_colors["folder_foreground"] = self.config.get("Colors", "folder_foreground", fallback=default_colors["folder_foreground"])
            
        return default_colors

    def select_folder(self):
        folder = filedialog.askdirectory(initialdir=self.current_folder)
        if folder:
            self.current_folder = folder
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()

    # Loads all supported files and (optionally) folders from the current folder,
    # applies the selected sort method, and updates the file list display.
    def load_images(self):
        # Start timer if debugging
        if self.debug_mode:
            self._load_timer_start = time.perf_counter()

        # Show "Loading..." in the status bar immediately
        self.status_label.config(text="Loading...")
        self.root.update_idletasks()
        
        try:
            sort_method = self.sort_var.get() if hasattr(self, 'sort_var') else "Name"
            ascending = getattr(self, 'sort_ascending', True)

            all_entries = []
            filenames = os.listdir(self.current_folder)

            # Phase 1: Collect files
            for name in filenames:
                full_path = os.path.join(self.current_folder, name)

                if os.path.isfile(full_path) and name.lower().endswith(self.supported_formats):
                    all_entries.append({
                        "name": name,
                        "is_folder": False,
                        "size": 0,
                        "created": 0,
                        "modified": 0
                    })

            # Phase 2: Collect folders (if enabled)
            if self.show_folders:
                for name in filenames:
                    full_path = os.path.join(self.current_folder, name)

                    if not os.path.isdir(full_path):
                        continue

                    if name.startswith('.') or self.is_hidden_or_system(full_path):
                        continue

                    all_entries.append({
                        "name": name,
                        "is_folder": True,
                        "size": 0,
                        "created": 0,
                        "modified": 0
                    })

            # Phase 3: If sorting by anything other than name, fetch extra metadata
            if sort_method in {"Size", "Created", "Modified"}:
                for entry in all_entries:
                    full_path = os.path.join(self.current_folder, entry["name"])
                    try:
                        entry["size"] = os.path.getsize(full_path)
                        entry["created"] = os.path.getctime(full_path)
                        entry["modified"] = os.path.getmtime(full_path)
                    except Exception:
                        continue  # skip bad entries

            def sort_key(entry):
                if sort_method == "Size":
                    return entry["size"]
                elif sort_method == "Created":
                    return entry["created"]
                elif sort_method == "Modified":
                    return entry["modified"]
                else:
                    return entry["name"].lower()

            sorted_entries = sorted(
                all_entries,
                key=lambda e: (0 if e["is_folder"] else 1, sort_key(e)),
                reverse=not ascending
            )

            self.all_files = [entry["name"] for entry in sorted_entries]

        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Error reading folder:\n{e}",
                fill="white", font=("Arial", 14)
            )
            return

        self.update_file_list()

    # Updates the Listbox to show files and (optionally) folders matching the current search.
    # Applies alternating background colors and foreground colors based on file type.
    def update_file_list(self, *args):
        self.listbox.delete(0, tk.END)
        self.current_image_path = None
        self.canvas.delete("all")

        query = self.search_var.get().strip().lower().split()

        def match_all_terms(filename):
            name = filename.lower()
            return all(term in name for term in query)

        matching_files = [f for f in self.all_files if match_all_terms(f)]

        for index, file in enumerate(matching_files):
            self.listbox.insert(tk.END, file)
            bg = self.colors["list_background"] if index % 2 == 0 else self.colors["list_background_alt"]

            # Check if this is an image or a folder
            file_path = os.path.join(self.current_folder, file)
            is_folder = os.path.isdir(file_path)
            file_path = os.path.join(self.current_folder, file)
            is_folder = os.path.isdir(file_path)

            # Folders appear in a different colour
            if is_folder:
                fg = self.colors["folder_foreground"]
            else:
                fg = self.colors["foreground"]


            self.listbox.itemconfig(index, {'bg': bg, 'fg': fg})

        if matching_files:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.listbox.event_generate("<<ListboxSelect>>")
        else:
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text="No matching files.",
                fill="white", font=("Arial", 14)
            )

        # If DebugMode = true display the timer
        if self.debug_mode and hasattr(self, "_load_timer_start"):
            elapsed = time.perf_counter() - self._load_timer_start
            del self._load_timer_start
            self.status_label.config(text=f"Loaded folder {self.current_folder} in {elapsed:.3f} seconds.")
        else:
            self.status_label.config(text="")

    def refresh_folder(self, event=None):
        self.load_images()

    def show_selected_image(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return

        filename = self.listbox.get(selection[0])
        filepath = os.path.join(self.current_folder, filename)

        try:
            Image.open(filepath).verify()
            self.current_image_path = filepath
            self.render_image()
        except Exception:
            self.current_image_path = None
            self.canvas.delete("all")  # 👈 Clear stale image

    def on_canvas_resize(self, event):
        if self.current_image_path:
            self.render_image()

    def render_image(self):
        try:
            img = Image.open(self.current_image_path)
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            img_ratio = img.width / img.height
            canvas_ratio = canvas_width / canvas_height

            if img_ratio > canvas_ratio:
                new_width = canvas_width
                new_height = int(new_width / img_ratio)
            else:
                new_height = canvas_height
                new_width = int(new_height * img_ratio)

            img = img.resize((new_width, new_height), Image.LANCZOS)
            self.current_image = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                anchor=tk.CENTER, image=self.current_image
            )
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Error loading image:\n{e}",
                fill="white", font=("Arial", 14)
            )

    def prompt_delete_selected_files(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        confirm = messagebox.askyesno("Delete Files", "Are you sure you want to delete the selected files?")
        if not confirm:
            return

        filenames = [self.listbox.get(i) for i in selection]
        start_index = selection[0]

        dialog, label, progress = self.show_status_dialog("Deleting Files", filenames)

        for i, filename in enumerate(filenames):
            label.config(text=filename)
            dialog.update_idletasks()

            path = os.path.join(self.current_folder, filename)
            try:
                os.remove(path)
            except Exception as e:
                messagebox.showerror("Delete Failed", f"Could not delete {filename}:\n{e}")

            progress["value"] = i + 1

        dialog.destroy()
        self.load_images()

        # Try to restore selection near previous location
        num_items = self.listbox.size()
        if num_items > 0:
            restored_index = min(start_index, num_items - 1)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(restored_index)
            self.listbox.activate(restored_index)
            self.listbox.see(restored_index)
            self.listbox.focus_set()
            self.listbox.event_generate("<<ListboxSelect>>")

    def move_files_to_folder(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        target_dir = filedialog.askdirectory(title="Select Destination Folder")
        if not target_dir:
            return

        filenames = [self.listbox.get(i) for i in selection]
        dialog, label, progress = self.show_status_dialog("Moving Files", filenames)

        for i, filename in enumerate(filenames):
            label.config(text=filename)
            dialog.update_idletasks()
            source = os.path.join(self.current_folder, filename)
            dest = os.path.join(target_dir, filename)
            try:
                shutil.move(source, dest)
            except Exception as e:
                messagebox.showerror("Move Failed", f"Failed to move {filename}:\n{e}")
            progress["value"] = i + 1

        dialog.destroy()

        self.load_images()

    def copy_files_to_folder(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        target_dir = filedialog.askdirectory(title="Select Destination Folder")
        if not target_dir:
            return

        filenames = [self.listbox.get(i) for i in selection]
        dialog, label, progress = self.show_status_dialog("Copying Files", filenames)

        for i, filename in enumerate(filenames):
            label.config(text=filename)
            dialog.update_idletasks()
            source = os.path.join(self.current_folder, filename)
            dest = os.path.join(target_dir, filename)
            try:
                shutil.copy2(source, dest)
            except Exception as e:
                messagebox.showerror("Copy Failed", f"Failed to copy {filename}:\n{e}")
            progress["value"] = i + 1

        dialog.destroy()

    def rewrite_file_names(self, event=None):

        selection = self.listbox.curselection()
        if not selection:
            return

        for i in selection:
            # Pull the escape hatch if this is a folder
            file_path = os.path.join(self.current_folder, self.listbox.get(i))
            if os.path.isdir(file_path):
                return
                    
            original_filename = self.listbox.get(i)
            new_filename = scrub_filename(original_filename)

            if new_filename != original_filename:
                old_path = os.path.join(self.current_folder, original_filename)
                new_path = os.path.join(self.current_folder, new_filename)

                if os.path.exists(new_path):
                    messagebox.showerror("Rename Failed", f"{new_filename} already exists.")
                    continue

                try:
                    os.rename(old_path, new_path)
                except Exception as e:
                    messagebox.showerror("Rename Failed", f"Failed to rename {original_filename}:\n{e}")
        self.load_images()

    def prompt_rename_selected_file(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        old_name = self.listbox.get(selection[0])
        old_path = os.path.join(self.current_folder, old_name)
        new_name = simpledialog.askstring("Rename File", f"Enter new name for:\n{old_name}", initialvalue=old_name)
        if not new_name or new_name.strip() == "":
            return
        new_path = os.path.join(self.current_folder, new_name)
        if os.path.exists(new_path):
            messagebox.showerror("Rename Failed", "A file with that name already exists.")
            return
        try:
            os.rename(old_path, new_path)
            self.load_images()
        except Exception as e:
            messagebox.showerror("Rename Failed", f"Unable to rename file:\n{e}")

    # User pressed Enter.  If it's an image display it.  If it's not, launch its program.  If it's a folder enter it.
    def show_fullscreen_image(self, event=None):
        selection = self.listbox.curselection()
        if len(selection) != 1:
            return

        filename = self.listbox.get(selection[0])
        full_path = os.path.join(self.current_folder, filename)

        if os.path.isdir(full_path):
            self.current_folder = full_path
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()
            return

        try:
            img = Image.open(full_path)
        except Exception:
            # Not a valid image — launch with default program
            self.status_label.config(text=f"Launching {filename}...")
            self.root.update_idletasks()
            os.startfile(full_path)
            return

        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            img_ratio = img.width / img.height
            screen_ratio = screen_width / screen_height
            if img_ratio > screen_ratio:
                new_width = screen_width
                new_height = int(new_width / img_ratio)
            else:
                new_height = screen_height
                new_width = int(new_height * img_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            fullscreen_img = ImageTk.PhotoImage(img)
            if self.fullscreen_window and self.fullscreen_window.winfo_exists():
                self.fullscreen_window.destroy()
            self.fullscreen_window = tk.Toplevel(self.root)
            self.fullscreen_window.attributes("-fullscreen", True)
            self.fullscreen_window.configure(bg="black")
            self.fullscreen_window.focus_set()
            self.fullscreen_window.bind("<Escape>", lambda e: self.fullscreen_window.destroy())
            self.fullscreen_window.bind("<Left>", self.fullscreen_previous_image)
            self.fullscreen_window.bind("<Right>", self.fullscreen_next_image)
            label = tk.Label(self.fullscreen_window, image=fullscreen_img, bg="black")
            label.image = fullscreen_img
            label.pack(expand=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not display fullscreen image:\n\n{e}")

    # We're displaying an image.  Switch to fullscreen mode.
    def open_fullscreen_window(self):
        try:
            image_name = self.fullscreen_images[self.fullscreen_index]
            full_path = os.path.join(self.current_folder, image_name)
            try:
                img = Image.open(full_path)
            except Exception:
                os.startfile(full_path)
                return
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            img_ratio = img.width / img.height
            screen_ratio = screen_width / screen_height
            if img_ratio > screen_ratio:
                new_width = screen_width
                new_height = int(new_width / img_ratio)
            else:
                new_height = screen_height
                new_width = int(new_height * img_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            fullscreen_img = ImageTk.PhotoImage(img)
            if self.fullscreen_window and self.fullscreen_window.winfo_exists():
                self.fullscreen_window.destroy()
            self.fullscreen_window = tk.Toplevel(self.root)
            self.fullscreen_window.attributes("-fullscreen", True)
            self.fullscreen_window.configure(bg="black")
            self.fullscreen_window.focus_set()
            self.fullscreen_window.bind("<Escape>", lambda e: self.fullscreen_window.destroy())
            self.fullscreen_window.bind("<Left>", self.fullscreen_previous_image)
            self.fullscreen_window.bind("<Right>", self.fullscreen_next_image)
            label = tk.Label(self.fullscreen_window, image=fullscreen_img, bg="black")
            label.image = fullscreen_img
            label.pack(expand=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not display fullscreen image:\n\n{e}")

# Main program loop
if __name__ == "__main__":
    root = tk.Tk()
    root.state('zoomed')
    app = ImageBrowserApp(root)
    root.mainloop()
