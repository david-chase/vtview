import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from functools import partial
import configparser
import re
import webbrowser

def scrub_filename(filename: str) -> str:
    base, ext = os.path.splitext(filename)
    match = re.search(r"(.*?)(\s*)(#.+)", base)
    if not match:
        return filename
    root_part = match.group(1).rstrip()
    tag_part = match.group(3)
    hashtags = [tag.lower() for tag in re.findall(r"#\w+", tag_part)]
    priority_tags = {"#1", "#2", "#3", "#4", "#5"}
    last_priority_tag = None
    other_tags = []
    for tag in hashtags:
        if tag in priority_tags:
            last_priority_tag = tag
        else:
            other_tags.append(tag)
    unique_other_tags = sorted(set(other_tags))
    all_tags = ([last_priority_tag] if last_priority_tag else []) + unique_other_tags
    new_tag_string = "".join(all_tags)
    return f"{root_part} {new_tag_string}{ext}"

class ImageBrowserApp:
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

    def on_listbox_motion(self, event):
        index = self.listbox.nearest(event.y)

        # If same index as before, do nothing
        if self.tooltip_index == index:
            return

        self.hide_tooltip()  # Cancel previous tooltip if any
        self.tooltip_index = index

        # Schedule new tooltip
        self.tooltip_after_id = self.root.after(1000, lambda: self.show_tooltip(event, index))

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
        selection = self.listbox.curselection()
        if not selection:
            return

        tag = self.ask_tag_with_autocomplete()
        if not tag:
            return

        tag = tag.strip()
        if not tag.startswith("#"):
            tag = f"#{tag}"

        filenames = [self.listbox.get(i) for i in selection]
        updated_filenames = []
        dialog, label, progress = self.show_status_dialog("Adding Tag", filenames)

        for i, filename in enumerate(filenames):
            label.config(text=filename)
            dialog.update_idletasks()

            base, ext = os.path.splitext(filename)
            new_filename = scrub_filename(f"{base} {tag}{ext}")
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

    def _tag_shortcut_handler(self, tag_value, event=None):
        self.tag_file_with_priority(str(tag_value))

    def __init__(self, root):
        self.root = root
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.script_dir, "vtview.ini")
        self.config = self.load_config()

        self.colors = self.get_colors()

        self.supported_formats = self.get_supported_extensions()
        self.shortcut_keys = self.get_shortcuts()
        self.default_folder = self.config.get("Settings", "default_folder", fallback=os.getcwd())

        self.current_folder = self.default_folder
        self.root.title(f"VtView - {self.current_folder}")
        self.root.configure(bg=self.colors["background"])

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

        self.select_button = tk.Button(
            folder_sort_frame,
            text="Select",
            width=6,
            bg=self.colors["button_background"],
            fg=self.colors["button_foreground"],
            activebackground=self.colors["highlight"],
            command=self.select_folder
        )
        self.select_button.pack(side=tk.LEFT)

        tk.Label(
            folder_sort_frame,
            text="Sort by:",
            bg=self.colors["background"],
            fg=self.colors["foreground"]
        ).pack(side=tk.LEFT, padx=(10, 2))

        self.sort_var = tk.StringVar(value="Name")
        self.sort_dropdown = ttk.Combobox(
            folder_sort_frame,
            textvariable=self.sort_var,
            values=["Name", "Size", "Created", "Modified"],
            state="readonly",
            width=10
        )
        self.sort_dropdown.pack(side=tk.LEFT)
        self.sort_dropdown.bind("<<ComboboxSelected>>", lambda e: self.load_images())


        listbox_frame = tk.Frame(self.left_frame, bg=self.colors["foreground"], bd=1, relief="solid")
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=(0,0), pady=(10,5))

        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            listbox_frame,
            selectmode=tk.EXTENDED,
            bg=self.colors["list_background"],
            fg=self.colors["foreground"],
            selectbackground=self.colors["highlight"],
            highlightthickness=0,
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<<ListboxSelect>>", self.show_selected_image)

        self.tooltip_window = None
        self.tooltip_after_id = None
        self.tooltip_index = None

        self.listbox.bind("<Motion>", self.on_listbox_motion)
        self.listbox.bind("<Leave>", self.hide_tooltip)


        self.right_frame = tk.Frame(self.paned, bg=self.colors["background"])
        self.paned.add(self.right_frame)

        self.canvas = tk.Canvas(self.right_frame, bg=self.colors["canvas_background"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=(0,0), pady=(10,5))

        self.current_image = None
        self.current_image_path = None
        self.fullscreen_window = None
        self.all_files = []

        self.load_images()
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        style = ttk.Style()
        style.theme_use("clam")  # looks good in dark mode
        style.configure("Vertical.TScrollbar",
            background=self.colors["button_background"],
            troughcolor=self.colors["background"],
            bordercolor=self.colors["background"],
            arrowcolor=self.colors["foreground"]
        )

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
            "open_help": self.open_help_url
        }

        for keyname, handler in keymap.items():
            raw_key = self.shortcut_keys.get(keyname)
            if raw_key:
                binding = self.normalize_binding(raw_key)

                # Return 'break' to suppress default widget behavior
                def wrapped_handler(event, h=handler):
                    h()
                    return "break"

                self.listbox.bind(binding, wrapped_handler)
                self.search_entry.bind(binding, wrapped_handler)

        for i in range(1, 6):
            raw_key = self.shortcut_keys.get(f"alt_tag_{i}", f"Alt-{i}")
            binding = self.normalize_binding(raw_key)
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

    def tag_file_with_priority(self, tag_value):
        selection = self.listbox.curselection()
        if not selection:
            return

        updated_filenames = []

        for i in selection:
            original_filename = self.listbox.get(i)
            base, ext = os.path.splitext(original_filename)
            modified_filename = f"{base} #{tag_value}{ext}"
            cleaned_filename = scrub_filename(modified_filename)

            if cleaned_filename == original_filename:
                continue

            old_path = os.path.join(self.current_folder, original_filename)
            new_path = os.path.join(self.current_folder, cleaned_filename)

            if os.path.exists(new_path):
                messagebox.showerror("Rename Failed", f"{cleaned_filename} already exists.")
                continue

            try:
                os.rename(old_path, new_path)
                updated_filenames.append(cleaned_filename)
            except Exception as e:
                messagebox.showerror("Rename Failed", f"Failed to apply tag #{tag_value} to {original_filename}:\n{e}")

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


    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        return config

    def get_supported_extensions(self):
        extensions = self.config.get("Settings", "extensions", fallback=".jpg,.jpeg,.gif,.webp,.png")
        video_extensions = self.config.get("Sections", "videoextensions", fallback=".mp4,.avi,.webm").lower()

        self.video_extensions = tuple(e.strip().lower() for e in video_extensions.split(",") if e.strip())
        return tuple(e.strip().lower() for e in extensions.split(",") if e.strip())


    def get_shortcuts(self):
        return dict(self.config.items("Shortcuts")) if self.config.has_section("Shortcuts") else {}

    def get_colors(self):
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
            "invalid_foreground": "#888888"
        }
        if self.config.has_section("Colors"):
            for key in default_colors:
                default_colors[key] = self.config.get("Colors", key, fallback=default_colors[key])
        
            # Optional extensions
            default_colors["list_background"] = self.config.get("Colors", "list_background", fallback=default_colors["background"])
            default_colors["canvas_background"] = self.config.get("Colors", "canvas_background", fallback=default_colors["background"])        
            default_colors["invalid_foreground"] = self.config.get("Colors", "invalid_foreground", fallback=default_colors["invalid_foreground"])
            
        return default_colors

    def select_folder(self):
        folder = filedialog.askdirectory(initialdir=self.current_folder)
        if folder:
            self.current_folder = folder
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()

    def load_images(self):
        try:
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

            sort_method = self.sort_var.get() if hasattr(self, 'sort_var') else "Name"
            file_list = [f for f in os.listdir(self.current_folder) if f.lower().endswith(self.supported_formats)]
            sort_key = self.sort_key_factory(sort_method)
            self.all_files = sorted(file_list, key=sort_key)

        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Error reading folder:\n{e}",
                fill="white", font=("Arial", 14)
            )
            return
        self.update_file_list()

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

            file_path = os.path.join(self.current_folder, file)
            is_image = True
            file_ext = os.path.splitext(file)[1].lower()
            is_image = file_ext in self.supported_formats

            fg = self.colors["foreground"] if is_image else self.colors["invalid_foreground"]
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

    def show_fullscreen_image(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        self.fullscreen_index = selection[0]
        self.fullscreen_images = self.listbox.get(0, tk.END)
        self.open_fullscreen_window()

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


if __name__ == "__main__":
    root = tk.Tk()
    root.state('zoomed')
    app = ImageBrowserApp(root)
    root.mainloop()
