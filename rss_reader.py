import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import feedparser
import webbrowser
from datetime import datetime
from dateutil.parser import parse as parse_date
from tkhtmlview import HTMLLabel
import html2text
from PIL import Image, ImageTk
import requests
from io import BytesIO
from tkinterweb import HtmlFrame

class RSSReader:
    def __init__(self, parent, db_path):
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("RSS Reader")
        
        # Tam ekran yerine sabit boyut ve merkezi konumlandırma
        window_width = 700
        window_height = 550
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Grid yapılandırması
        self.window.grid_rowconfigure(1, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_columnconfigure(1, weight=1)

        # Veritabanı başlatma ve read_links tablosunu temizleme
        self.initialize_db()
        self.clear_read_links() # Yeni eklenen metod
        self.read_items = set() # Artık veritabanından yüklemeye gerek yok

        # Üst çerçeve
        top_frame = ttk.Frame(self.window)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        ttk.Label(top_frame, text="RSS Kaynağı:").pack(side="left")
        self.feed_combobox = ttk.Combobox(top_frame, state="readonly")
        self.feed_combobox.pack(side="left", padx=5)
        self.load_feeds()

        ttk.Button(top_frame, text="Yükle", command=self.load_news).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Kaynak Ekle", command=self.add_feed).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Kaynak Sil", command=self.delete_feed).pack(side="left", padx=5)

        # Filtreleme frame - Resimleri Göster checkbox'ı kaldırıldı
        filter_frame = ttk.Frame(top_frame)
        filter_frame.pack(side="left", padx=10)
        self.show_unread_only = tk.BooleanVar()
        ttk.Checkbutton(filter_frame, text="Okunanları Gizle", 
                       variable=self.show_unread_only,
                       command=self.filter_news).pack(side="left")
        
        # Resimleri Göster seçeneği her zaman aktif
        self.show_images = tk.BooleanVar(value=True)

        # Sol panel
        left_panel = ttk.Frame(self.window)
        left_panel.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # Haber listesi
        self.tree = ttk.Treeview(left_panel, columns=("Title", "Date"), show="headings")
        self.tree.heading("Title", text="Başlık")
        self.tree.heading("Date", text="Yayın Tarihi")
        self.tree.column("Title", width=400)
        self.tree.column("Date", width=100)  # Tarih sütunu daraltıldı
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Özet sekmesi
        self.summary_frame = ttk.Frame(left_panel)
        self.summary_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        self.html_label = HTMLLabel(self.summary_frame, html="<p>Haber seçin...</p>", height=15)
        self.html_label.pack(fill="both", expand=True)
        self.text_widget = tk.Text(self.summary_frame, wrap="word", height=15, state="disabled")
        self.text_widget.pack(fill="both", expand=True)
        self.text_widget.pack_forget()

        # Sağ panel (browser frame)
        self.browser_frame = ttk.Frame(self.window)
        self.browser_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        # Sağ tık menüsü ve bağlantılar
        self.context_menu = tk.Menu(self.window, tearoff=0)
        self.context_menu.add_command(label="Tarayıcıda Aç", command=lambda: self.open_in_browser())

        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self.show_description)
        self.tree.bind("<Double-1>", lambda e: self.open_in_browser())

    def initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # rss_items tablosunu kaldır, sadece feeds ve read_links tablolarını tut
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rss_feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT UNIQUE NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS read_links (
                    link TEXT PRIMARY KEY
                )
            """)
            conn.commit()

    def clear_read_links(self):
        """RSS Reader açıldığında read_links tablosunu temizle"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM read_links")
                conn.commit()
        except sqlite3.Error as e:
            print(f"read_links tablosu temizlenirken hata: {e}")

    def load_read_items(self):
        """Artık veritabanından okumaya gerek yok, boş set döndür"""
        return set()

    def mark_as_read_db(self, link):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO read_links (link) VALUES (?)", (link,))
            conn.commit()

    def load_feeds(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM rss_feeds")
            feeds = [row[0] for row in cursor.fetchall()]
        self.feed_combobox["values"] = feeds
        if feeds:
            self.feed_combobox.current(0)

    def add_feed(self):
        dialog = tk.Toplevel(self.window)
        dialog.title("RSS Kaynağı Ekle")
        dialog.geometry("600x200")

        tk.Label(dialog, text="Ad:").pack(pady=5)
        name_entry = tk.Entry(dialog, width=60)  # 3 kat genişlik
        name_entry.pack(pady=5)
        tk.Label(dialog, text="URL:").pack(pady=5)
        url_entry = tk.Entry(dialog, width=60)  # 3 kat genişlik
        url_entry.pack(pady=5)

        def save_feed():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            if not name or not url:
                messagebox.showerror("Hata", "Ad ve URL alanları boş olamaz!")
                return
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO rss_feeds (name, url) VALUES (?, ?)", (name, url))
                    conn.commit()
                    self.load_feeds()
                    #messagebox.showinfo("Başarılı", "RSS kaynağı eklendi!")
                    dialog.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror("Hata", "Bu URL zaten mevcut!")

        tk.Button(dialog, text="Kaydet", command=save_feed).pack(pady=10)

    def delete_feed(self):
        selected_feed = self.feed_combobox.get()
        if not selected_feed:
            messagebox.showerror("Hata", "Lütfen bir kaynak seçin!")
            return
        if messagebox.askyesno("Onay", f"{selected_feed} kaynağını silmek istiyor musunuz?"):
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM rss_feeds WHERE name = ?", (selected_feed,))
                conn.commit()
                self.load_feeds()
                self.tree.delete(*self.tree.get_children())
                self.html_label.set_html("<p>Haber seçin...</p>")
                self.text_widget.config(state="normal")
                self.text_widget.delete("1.0", tk.END)
                self.text_widget.insert("1.0", "Haber seçin...")
                self.text_widget.config(state="disabled")
                # Tüm sekmeleri temizle
                for tab_id in self.notebook.tabs():
                    if self.notebook.tab(tab_id, "text") != "Özet":
                        self.notebook.forget(tab_id)
                messagebox.showinfo("Başarılı", "RSS kaynağı silindi!")

    def load_news(self):
        selected_feed = self.feed_combobox.get()
        if not selected_feed:
            messagebox.showerror("Hata", "Lütfen bir kaynak seçin!")
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM rss_feeds WHERE name = ?", (selected_feed,))
            url = cursor.fetchone()[0]

        try:
            feed = feedparser.parse(url)
            if feed.bozo:
                messagebox.showerror("Hata", "Geçersiz RSS kaynağı!")
                return

            self.tree.delete(*self.tree.get_children())
            self.news_items = []
            
            for entry in feed.entries:
                title = entry.get("title", "Başlık Yok")
                link = entry.get("link", "")
                description = entry.get("description", "")
                pub_date = entry.get("published", "") or entry.get("updated", "") or entry.get("pubDate", "")
                try:
                    parsed_date = parse_date(pub_date, fuzzy=True)
                    pub_date = parsed_date.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pub_date = "Bilinmiyor"

                self.news_items.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "description": description
                })

            self.filter_news()
        except Exception as e:
            messagebox.showerror("Hata", f"Haberler yüklenirken hata oluştu: {str(e)}")

    def filter_news(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.news_items:
            if self.show_unread_only.get() and item["link"] in self.read_items:
                continue
            tag = "unread" if item["link"] not in self.read_items else "read"
            self.tree.insert("", "end", values=(item["title"], item["pub_date"]), tags=(tag,))
        self.tree.tag_configure("unread", font=("Arial", 10, "bold"))
        self.tree.tag_configure("read", font=("Arial", 10))

    def show_description(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])["values"]
        title = item[0]
        for news_item in self.news_items:
            if news_item["title"] == title:
                description = news_item["description"] or "<p>Özet mevcut değil.</p>"
                
                # Önce okundu olarak işaretle
                if news_item["link"] not in self.read_items:
                    self.read_items.add(news_item["link"])
                    self.mark_as_read_db(news_item["link"])
                    self.filter_news()

                # Sonra özeti göster
                if self.show_images.get():
                    try:
                        self.html_label.pack(fill="both", expand=True)
                        self.text_widget.pack_forget()
                        self.html_label.set_html(description)
                    except Exception:
                        self.html_label.pack_forget()
                        self.text_widget.pack(fill="both", expand=True)
                        self.text_widget.config(state="normal")
                        self.text_widget.delete("1.0", tk.END)
                        h = html2text.HTML2Text()
                        h.ignore_images = True
                        plain_text = h.handle(description)
                        self.text_widget.insert("1.0", plain_text)
                        self.text_widget.config(state="disabled")
                else:
                    self.html_label.pack_forget()
                    self.text_widget.pack(fill="both", expand=True)
                    self.text_widget.config(state="normal")
                    self.text_widget.delete("1.0", tk.END)
                    h = html2text.HTML2Text()
                    h.ignore_images = True
                    plain_text = h.handle(description)
                    self.text_widget.insert("1.0", plain_text)
                    self.text_widget.config(state="disabled")
                break

    def open_in_new_tab(self, event):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])["values"]
        title = item[0]
        for news_item in self.news_items:
            if news_item["title"] == title:
                link = news_item["link"]
                if not link:
                    messagebox.showerror("Hata", "Bu haberin bağlantısı yok!")
                    return

                # Browser frame'i temizle ve yeni içeriği yükle
                for widget in self.browser_frame.winfo_children():
                    widget.destroy()

                try:
                    html_frame = HtmlFrame(self.browser_frame, messages_enabled=False)
                    html_frame.pack(fill="both", expand=True)
                    html_frame.load_website(link)
                except Exception as e:
                    error_label = tk.Label(self.browser_frame, text=f"İçerik yüklenemedi: {str(e)}")
                    error_label.pack(fill="both", expand=True)
                    tk.Button(self.browser_frame, text="Tarayıcıda Aç", 
                             command=lambda: webbrowser.open(link)).pack(pady=10)
                break

    def close_tab(self, tab_frame):
        self.notebook.forget(tab_frame)

    def show_context_menu(self, event):
        selected = self.tree.selection()
        if selected:
            self.context_menu.post(event.x_root, event.y_root)

    def open_in_browser(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])["values"]
        title = item[0]
        for news_item in self.news_items:
            if news_item["title"] == title:
                link = news_item["link"]
                if link:
                    try:
                        webbrowser.open(link)
                    except Exception as e:
                        messagebox.showerror("Hata", f"Link açılamadı: {e}", parent=self.window)
                else:
                    messagebox.showerror("Hata", "Bu haberin bağlantısı yok!", parent=self.window)
                break

if __name__ == "__main__":
    root = tk.Tk()
    app = RSSReader(root, "veriler.db")
    root.mainloop()