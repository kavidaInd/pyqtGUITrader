import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import logging
from urllib.parse import urlparse, parse_qs

from Utils.FyersManualLoginHelper import FyersManualLoginHelper

logger = logging.getLogger(__name__)


class FyersManualLoginPopup:
    def __init__(self, parent, brokerage_setting):
        self.parent = parent
        self.brokerage_setting = brokerage_setting

        self.window = tk.Toplevel(parent)
        self.window.title("Fyers Manual Login")
        self.window.geometry("520x280")
        self.window.resizable(False, False)
        self.window.configure(bg="#f4f6fa")
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(self.window, padding=18, style="Light.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        self.label = ttk.Label(
            frame,
            text="Step 1: Open the login URL in your browser and authorize.",
            style="Light.TLabel"
        )
        self.label.pack(anchor="w", pady=(0, 7))

        self.url_text = tk.Text(frame, height=2, width=60, wrap=tk.WORD, font=("Segoe UI", 10))
        self.url_text.pack(fill=tk.X, pady=(0, 7))
        self.url_text.configure(state="normal", cursor="arrow")  # make selectable
        self.url_text.bind("<1>", lambda event: self.url_text.focus_set())  # focus on click

        self.open_url_btn = ttk.Button(frame, text="🌐 Open Login URL", command=self.open_login_url)
        self.open_url_btn.pack(anchor="e", pady=(0, 10))

        self.auth_label = ttk.Label(
            frame,
            text="Step 2: Paste the full redirected URL (or just the code) here:",
            style="Light.TLabel"
        )
        self.auth_label.pack(anchor="w")

        self.code_entry = ttk.Entry(frame, width=58)
        self.code_entry.pack(anchor="w", pady=(2, 8))
        self.code_entry.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 0))

        self.login_btn = ttk.Button(btn_frame, text="🔒 Complete Login", command=self.exchange_code)
        self.login_btn.pack(side=tk.RIGHT)

        self.clear_btn = ttk.Button(btn_frame, text="✖ Clear", command=self.clear_code_entry)
        self.clear_btn.pack(side=tk.RIGHT, padx=(0, 10))

        self.fyers = None
        self.login_url = None
        self.init_login_url()

    def init_login_url(self):
        try:
            self.fyers = FyersManualLoginHelper(
                client_id=self.brokerage_setting.client_id,
                secret_key=self.brokerage_setting.secret_key,
                redirect_uri=self.brokerage_setting.redirect_uri
            )
            self.login_url = self.fyers.generate_login_url()
            self.url_text.configure(state="normal")
            self.url_text.delete(1.0, tk.END)
            self.url_text.insert(tk.END, self.login_url)
            self.url_text.configure(state="disabled")
        except Exception as e:
            logger.critical(f"Failed to generate login URL: {e!r}")
            messagebox.showerror("Error", f"Failed to generate login URL: {e}", parent=self.window)
            self.window.destroy()

    def open_login_url(self):
        if self.login_url:
            try:
                webbrowser.open(self.login_url)
            except Exception as e:
                logger.error(f"Failed to open URL in browser: {e}")
                messagebox.showerror("Error", "Failed to open URL in browser.", parent=self.window)
        else:
            messagebox.showerror("Error", "Login URL is unavailable.", parent=self.window)

    def exchange_code(self):
        code_or_url = self.code_entry.get().strip()
        if not code_or_url:
            messagebox.showwarning("Input Needed", "Please paste the auth code or full URL.", parent=self.window)
            return

        auth_code = self.extract_auth_code(code_or_url)
        if not auth_code:
            messagebox.showerror(
                "Error",
                "Could not extract auth code. Please paste the full redirected URL or just the code.",
                parent=self.window
            )
            return

        try:
            token = self.fyers.exchange_code_for_token(auth_code)
            if not token:
                logger.error("Failed to retrieve token. Please check the auth code and try again.")
                messagebox.showerror(
                    "Error",
                    "Failed to retrieve token. Please check the auth code and try again.",
                    parent=self.window
                )
                return

            logger.info(f"Token received: {token}")
            messagebox.showinfo("Success", "Login successful! Token received.", parent=self.window)
            self.window.destroy()
        except Exception as e:
            logger.critical(f"Exception during token exchange: {e!r}")
            messagebox.showerror(
                "Error",
                f"Exception during token exchange: {e}",
                parent=self.window
            )

    def clear_code_entry(self):
        self.code_entry.delete(0, tk.END)

    @staticmethod
    def extract_auth_code(input_text):
        # If input is raw code (no '=' or 'http'), just return it directly
        if "=" not in input_text and "http" not in input_text:
            return input_text.strip()

        try:
            if "auth_code=" in input_text:
                parsed = urlparse(input_text)
                query = parsed.query or parsed.fragment
                params = parse_qs(query)
                return params.get("auth_code", [None])[0]
        except Exception:
            return None
        return None

    def on_close(self):
        if messagebox.askokcancel("Quit", "Are you sure you want to cancel login?", parent=self.window):
            self.window.destroy()
