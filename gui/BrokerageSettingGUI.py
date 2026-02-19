import tkinter as tk
from tkinter import ttk, messagebox
import threading


class BrokerageSettingGUI:
    def __init__(self, parent, brokerage_setting):
        self.parent = parent
        self.brokerage_setting = brokerage_setting

        self.window = tk.Toplevel(parent)
        self.window.title("Brokerage Settings")
        self.window.geometry("420x300")
        self.window.configure(bg="#f4f6fa")
        self.window.resizable(False, False)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self.window, padding="24 18 24 18", style="Light.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(frame, text="🔑 Brokerage API Settings", font=("Segoe UI", 15, "bold"), style="Light.TLabel")
        header.grid(row=0, column=0, columnspan=2, pady=(0, 18))

        ttk.Label(frame, text="🆔 Client ID:", style="Light.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 10),
                                                                         pady=7)
        self.client_id_var = tk.StringVar(value=self.brokerage_setting.client_id)
        client_id_entry = ttk.Entry(frame, textvariable=self.client_id_var, width=30)
        client_id_entry.grid(row=2, column=1, sticky="w", pady=7)

        ttk.Label(frame, text="🔑 Secret Key:", style="Light.TLabel").grid(row=3, column=0, sticky="e", padx=(0, 10),
                                                                          pady=7)
        self.secret_key_var = tk.StringVar(value=self.brokerage_setting.secret_key)
        secret_key_entry = ttk.Entry(frame, textvariable=self.secret_key_var, show="*", width=30)
        secret_key_entry.grid(row=3, column=1, sticky="w", pady=7)

        ttk.Label(frame, text="🔗 Redirect URI:", style="Light.TLabel").grid(row=4, column=0, sticky="e", padx=(0, 10),
                                                                            pady=7)
        self.redirect_uri_var = tk.StringVar(value=self.brokerage_setting.redirect_uri)
        redirect_uri_entry = ttk.Entry(frame, textvariable=self.redirect_uri_var, width=30)
        redirect_uri_entry.grid(row=4, column=1, sticky="w", pady=7)

        # Set focus to first field
        client_id_entry.focus_set()

        # Save button
        btn = ttk.Button(frame, text="💾 Save", command=self.save)
        btn.grid(row=5, column=0, columnspan=2, pady=(20, 0), sticky="ew")

        # Key bindings
        self.window.bind("<Return>", lambda e: self.save())
        self.window.bind("<Escape>", lambda e: self._on_close())

    def save(self):
        # Collect and strip values
        client_id = self.client_id_var.get().strip()
        secret_key = self.secret_key_var.get().strip()
        redirect_uri = self.redirect_uri_var.get().strip()

        # Validation
        if not client_id or not secret_key or not redirect_uri:
            messagebox.showerror("Error", "All fields are required.", parent=self.window)
            return

        threading.Thread(target=self._threaded_save, args=(client_id, secret_key, redirect_uri), daemon=True).start()

    def _threaded_save(self, client_id, secret_key, redirect_uri):
        try:
            self.brokerage_setting.client_id = client_id
            self.brokerage_setting.secret_key = secret_key
            self.brokerage_setting.redirect_uri = redirect_uri

            self.brokerage_setting.save()
            # Schedule messagebox and window destruction on main thread
            self.window.after(0,
                              lambda: messagebox.showinfo("Success", "Brokerage settings saved!", parent=self.window))
            self.window.after(0, self.window.destroy)
        except Exception as e:
            self.window.after(0, lambda: messagebox.showerror("Error", f"Failed to save: {e}", parent=self.window))

    def _on_close(self):
        self.window.grab_release()
        self.window.destroy()
