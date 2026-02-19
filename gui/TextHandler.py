import logging
import tkinter as tk


class TextHandler(logging.Handler):
    """
    Custom logging handler that outputs log messages to a Tkinter Text widget,
    using colors appropriate for a dark-mode UI.
    """

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.configure(state='disabled')
        self._create_tags()

    def _create_tags(self):
        # Dark background, so use bright/contrasting colors for text
        self.text_widget.tag_config('INFO', foreground='#b0bec5')  # light gray-blue
        self.text_widget.tag_config('DEBUG', foreground='#78909c')  # muted blue-gray
        self.text_widget.tag_config('WARNING', foreground='#ffa726')  # orange
        self.text_widget.tag_config('ERROR', foreground='#ff4757')  # red
        self.text_widget.tag_config('CRITICAL', foreground='#ffffff', background='#ff4757', underline=True)
        self.text_widget.tag_config('DEFAULT', foreground='#b0bec5')  # fallback

    def emit(self, record):
        msg = self.format(record)
        level = record.levelname if record.levelname in self.text_widget.tag_names() else 'DEFAULT'

        def append():
            try:
                self.text_widget.configure(state='normal')
                self.text_widget.insert(tk.END, msg + '\n', level)
                self.text_widget.configure(state='disabled')
                self.text_widget.yview(tk.END)
            except (tk.TclError, RuntimeError):
                # Widget was likely destroyed
                pass
            except Exception as e:
                # Log to stderr or ignore
                print(f"TextHandler append error: {e}")

        # Only schedule append if widget still exists
        try:
            if self.text_widget.winfo_exists():
                self.text_widget.after(0, append)
        except Exception:
            pass

    def flush(self):
        pass
