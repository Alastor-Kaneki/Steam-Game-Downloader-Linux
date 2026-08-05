from .backend import *
from .backend import _extract_percent, _safe_name
from .ui import UiMixin


class App(UiMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1180x760")
        self.minsize(940, 620)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.runner = BackendRunner(lambda kind, value: self.events.put((kind, value)))
        self.config_path = app_config_dir() / "config.json"
        self.config_data = self._load_config()
        self.account_name = str(self.config_data.get("account", ""))
        self.apps: list[OwnedApp] = []
        self.filtered_apps: list[OwnedApp] = []
        self.qr_url = ""
        self.current_purpose = ""

        self._setup_style()
        self._build_ui()
        self.after(75, self._drain_events)
        self.after(150, self._startup)

    def _load_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text("utf-8"))
        except Exception:
            return {}

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_data.update(
            {
                "account": self.account_name,
                "destination": self.destination_var.get(),
                "os": self.os_var.get(),
                "arch": self.arch_var.get(),
                "language": self.language_var.get(),
                "branch": self.branch_var.get(),
            }
        )
        self.config_path.write_text(json.dumps(self.config_data, indent=2), "utf-8")

    def _startup(self) -> None:
        backend = find_backend()
        if backend is None:
            self.status_label.configure(text="Backend missing — use the AppImage build or set STEAM_DL_BACKEND")
            self._append_log("Patched DepotDownloader backend not found.")
            return
        valid, detail = verify_backend(backend)
        if not valid:
            self.status_label.configure(text="Incompatible backend — use the packaged AppImage backend")
            self._append_log(f"Backend verification failed: {detail}")
            return
        self._append_log(f"Backend: {backend} (GUI protocol {detail})")
        if self.account_name:
            self.account_label.configure(text=f"Steam: {self.account_name}")
            self.refresh_library()

    def _drain_events(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(kind, value)
        self.after(75, self._drain_events)

    def _handle_event(self, kind: str, value: object) -> None:
        if kind == "log":
            self._append_log(str(value))
        elif kind == "qr":
            self.qr_url = str(value)
            self._draw_qr(self.qr_url)
            if not self.qr_card.winfo_ismapped():
                self.qr_card.pack(fill="x", before=self.log.master, pady=(8, 4))
            self.status_label.configure(text="Scan the QR code with Steam Mobile")
        elif kind == "account":
            self.account_name = str(value)
            self.account_label.configure(text=f"Steam: {self.account_name}")
            self._save_config()
        elif kind == "library":
            self.apps = list(value)  # type: ignore[arg-type]
            self._apply_filter()
            self.status_label.configure(text=f"Loaded {len(self.apps)} owned apps")
            self.qr_card.pack_forget()
            self._save_config()
        elif kind == "progress":
            self.progress.stop()
            self.progress.configure(mode="determinate", value=float(value))
        elif kind == "error":
            self._append_log("ERROR: " + str(value))
            messagebox.showerror(APP_NAME, str(value), parent=self)
        elif kind == "done":
            purpose, code = value  # type: ignore[misc]
            self.current_purpose = ""
            self.progress.stop()
            if purpose == "download" and code == 0:
                self.progress.configure(mode="determinate", value=100)
                self.status_label.configure(text="Download completed")
            elif code != 0:
                self.status_label.configure(text=f"Operation failed with exit code {code}")
            else:
                self.status_label.configure(text="Ready")

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _draw_qr(self, payload: str) -> None:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=4, box_size=1)
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        size = len(matrix)
        canvas_size = 300
        scale = max(1, canvas_size // size)
        actual = size * scale
        offset = (canvas_size - actual) // 2
        self.qr_canvas.delete("all")
        self.qr_canvas.create_rectangle(0, 0, canvas_size, canvas_size, fill="#ffffff", outline="#ffffff")
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    x0 = offset + x * scale
                    y0 = offset + y * scale
                    self.qr_canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, fill="#000000", outline="#000000")

    def _apply_filter(self) -> None:
        query = self.search_var.get().strip().casefold()
        if query:
            self.filtered_apps = [app for app in self.apps if query in app.name.casefold() or query in str(app.app_id) or query in app.app_type.casefold()]
        else:
            self.filtered_apps = list(self.apps)
        self.tree.delete(*self.tree.get_children())
        for app in self.filtered_apps:
            self.tree.insert("", "end", iid=str(app.app_id), values=(app.name, app.app_id, app.app_type or "app"))

    def _selection_changed(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        app_id = int(selected[0])
        app = next((item for item in self.apps if item.app_id == app_id), None)
        if app:
            self.details_title.configure(text=app.name)
            self.details_meta.configure(text=f"AppID {app.app_id} • {app.app_type or 'app'}")

    def selected_app(self) -> OwnedApp | None:
        selected = self.tree.selection()
        if not selected:
            return None
        app_id = int(selected[0])
        return next((item for item in self.apps if item.app_id == app_id), None)

    def _begin(self, args: list[str], purpose: str, status: str) -> None:
        if self.runner.running:
            messagebox.showwarning(APP_NAME, "Another Steam operation is already running.", parent=self)
            return
        self.current_purpose = purpose
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self.status_label.configure(text=status)
        try:
            self.runner.start(args, purpose)
        except Exception as exc:
            self.progress.stop()
            self.current_purpose = ""
            messagebox.showerror(APP_NAME, str(exc), parent=self)

    def qr_login(self) -> None:
        self.apps.clear()
        self._apply_filter()
        self.account_name = ""
        self.account_label.configure(text="Waiting for Steam QR login")
        self._begin(["-list-owned-json", "-qr", "-remember-password"], "library", "Starting Steam QR login…")

    def refresh_library(self) -> None:
        if not self.account_name:
            self.qr_login()
            return
        self._begin(["-list-owned-json", "-username", self.account_name, "-remember-password"], "library", "Loading owned library…")

    def download_selected(self) -> None:
        app = self.selected_app()
        if app is None:
            messagebox.showinfo(APP_NAME, "Select an owned game or app first.", parent=self)
            return
        if not self.account_name:
            messagebox.showinfo(APP_NAME, "Sign in with the Steam QR code first.", parent=self)
            return
        destination = Path(self.destination_var.get()).expanduser()
        destination.mkdir(parents=True, exist_ok=True)
        args = [
            "-app", str(app.app_id),
            "-username", self.account_name,
            "-remember-password",
            "-dir", str(destination / _safe_name(app.name)),
            "-os", self.os_var.get(),
            "-osarch", self.arch_var.get(),
            "-language", self.language_var.get().strip() or "english",
            "-branch", self.branch_var.get().strip() or "public",
        ]
        self._save_config()
        self._begin(args, "download", f"Downloading {app.name}…")

    def cancel_operation(self) -> None:
        if self.runner.running:
            self.status_label.configure(text="Cancelling…")
            self.runner.stop()

    def choose_destination(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.destination_var.get() or str(Path.home()), parent=self)
        if selected:
            self.destination_var.set(selected)
            self._save_config()

    def open_destination(self) -> None:
        path = Path(self.destination_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open the folder: {exc}", parent=self)

    def logout(self) -> None:
        if self.runner.running:
            self.runner.stop()
        if not messagebox.askyesno(APP_NAME, "Remove the saved Steam session from this app?", parent=self):
            return
        shutil.rmtree(backend_state_root(), ignore_errors=True)
        self.account_name = ""
        self.apps.clear()
        self._apply_filter()
        self.account_label.configure(text="Not signed in")
        self.details_title.configure(text="Select an owned game")
        self.details_meta.configure(text="")
        self.config_data.pop("account", None)
        self._save_config()
        self.status_label.configure(text="Signed out")

    def on_close(self) -> None:
        self._save_config()
        self.runner.stop()
        self.destroy()



def main() -> None:
    app = App()
    app.mainloop()
