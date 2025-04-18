import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import configparser

class ImageBrowserApp:
    def __init__(self, root):
        self.root = root
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.script_dir, "vtview.ini")
        self.config = self.load_config()

        self.supported_formats = self.get_supported_extensions()
        self.shortcut_keys = self.get_shortcuts()
        self.default_folder = self.config.get("Settings", "default_folder", fallback=os.getcwd())

        self.current_folder = self.default_folder
        self.root.title(f"VtView - {self.current_folder}")

        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.paned, width=200)
        self.paned.add(self.left_frame, minsize=100)

        self.select_button = ttk.Button(self.left_frame, text="Select Folder", command=self.select_folder)
        self.select_button.pack(padx=10, pady=(10, 0), fill=tk.X)

        self.listbox = tk.Listbox(self.left_frame)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.listbox.bind("<<ListboxSelect>>", self.show_selected_image)

        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame)

        self.canvas = tk.Canvas(self.right_frame, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.current_image = None
        self.current_image_path = None
        self.fullscreen_window = None

        self.load_images()
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        delete_key = self.shortcut_keys.get("delete_file", "Delete")
        refresh_key = self.shortcut_keys.get("refresh_folder", "F5")
        rename_key = self.shortcut_keys.get("rename_file", "F2")
        fullscreen_key = self.shortcut_keys.get("fullscreen_view", "Return")
        move_key = self.shortcut_keys.get("move_file", "Alt-m")
        copy_key = self.shortcut_keys.get("copy_file", "Alt-c")

        self.root.bind(f"<{delete_key}>", self.prompt_delete_selected_file)
        self.root.bind(f"<{refresh_key}>", self.refresh_folder)
        self.root.bind(f"<{rename_key}>", self.prompt_rename_selected_file)
        self.root.bind(f"<{fullscreen_key}>", self.show_fullscreen_image)
        self.root.bind(f"<{move_key}>", self.move_file_to_folder)
        self.root.bind(f"<{copy_key}>", self.copy_file_to_folder)

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        return config

    def get_supported_extensions(self):
        extensions = self.config.get("Settings", "extensions", fallback=".jpg,.jpeg,.gif,.webp,.png")
        return tuple(e.strip().lower() for e in extensions.split(",") if e.strip())

    def get_shortcuts(self):
        return dict(self.config.items("Shortcuts")) if self.config.has_section("Shortcuts") else {}

    def select_folder(self):
        folder = filedialog.askdirectory(initialdir=self.current_folder)
        if folder:
            self.current_folder = folder
            self.root.title(f"VtView - {self.current_folder}")
            self.load_images()

    def load_images(self):
        self.listbox.delete(0, tk.END)
        self.current_image_path = None
        self.canvas.delete("all")

        try:
            image_files = [
                f for f in sorted(os.listdir(self.current_folder))
                if f.lower().endswith(self.supported_formats)
            ]
            for file in image_files:
                self.listbox.insert(tk.END, file)

            if image_files:
                self.listbox.selection_set(0)
                self.listbox.activate(0)
                self.listbox.event_generate("<<ListboxSelect>>")
            else:
                self.canvas.create_text(
                    10, 10, anchor=tk.NW,
                    text="No supported image files in this folder.",
                    fill="white",
                    font=("Arial", 14)
                )
        except Exception as e:
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Error reading folder:\n{e}",
                fill="white",
                font=("Arial", 14)
            )

    def refresh_folder(self, event=None):
        self.load_images()

    def show_selected_image(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        filename = self.listbox.get(selection[0])
        self.current_image_path = os.path.join(self.current_folder, filename)
        self.render_image()

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
                canvas_width // 2,
                canvas_height // 2,
                anchor=tk.CENTER,
                image=self.current_image
            )
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor=tk.NW,
                text=f"Error loading image:\n{e}",
                fill="white",
                font=("Arial", 14)
            )

    def prompt_delete_selected_file(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        filename = self.listbox.get(selection[0])
        full_path = os.path.join(self.current_folder, filename)

        confirm = messagebox.askyesno("Delete File", f"Are you sure you want to delete:\n\n{filename}?")
        if confirm:
            try:
                os.remove(full_path)
                self.load_images()
                self.canvas.delete("all")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete file:\n\n{e}")

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
            if new_name.lower().endswith(self.supported_formats):
                index = self.listbox.get(0, tk.END).index(new_name)
                self.listbox.selection_set(index)
                self.listbox.activate(index)
                self.show_selected_image(None)
        except Exception as e:
            messagebox.showerror("Rename Failed", f"Unable to rename file:\n{e}")

    def move_file_to_folder(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        filename = self.listbox.get(selection[0])
        full_path = os.path.join(self.current_folder, filename)

        target_dir = filedialog.askdirectory(title="Select Destination Folder")
        if not target_dir:
            return

        target_path = os.path.join(target_dir, filename)

        if os.path.exists(target_path):
            messagebox.showerror("Move Failed", "A file with the same name already exists in the target folder.")
            return

        try:
            shutil.move(full_path, target_path)
            self.load_images()
        except Exception as e:
            messagebox.showerror("Move Failed", f"Failed to move file:\n{e}")

    def copy_file_to_folder(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return

        filename = self.listbox.get(selection[0])
        full_path = os.path.join(self.current_folder, filename)

        target_dir = filedialog.askdirectory(title="Select Destination Folder")
        if not target_dir:
            return

        target_path = os.path.join(target_dir, filename)

        if os.path.exists(target_path):
            messagebox.showerror("Copy Failed", "A file with the same name already exists in the target folder.")
            return

        try:
            shutil.copy2(full_path, target_path)
        except Exception as e:
            messagebox.showerror("Copy Failed", f"Failed to copy file:\n{e}")

    def show_fullscreen_image(self, event=None):
        if not self.current_image_path:
            return

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
            img = Image.open(full_path)
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

            if self.fullscreen_window is not None and self.fullscreen_window.winfo_exists():
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

    def fullscreen_previous_image(self, event=None):
        if self.fullscreen_index > 0:
            self.fullscreen_index -= 1
            self.open_fullscreen_window()

    def fullscreen_next_image(self, event=None):
        if self.fullscreen_index < len(self.fullscreen_images) - 1:
            self.fullscreen_index += 1
            self.open_fullscreen_window()

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageBrowserApp(root)
    root.geometry("900x650")
    root.mainloop()
