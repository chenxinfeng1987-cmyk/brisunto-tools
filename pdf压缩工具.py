import os, io, tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image

def compress_pdf(filepath, dpi=80, quality=45):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(filepath)
    n = len(pdf)
    if n == 0:
        return None
    jpegs = []
    for i in range(n):
        page = pdf[i]
        bm = page.render(scale=dpi/72)
        img = bm.to_pil().convert('RGB')
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True)
        jpegs.append(buf.getvalue())
        page.close()
    pdf.close()
    out_buf = io.BytesIO()
    import img2pdf
    out_buf.write(img2pdf.convert(jpegs))
    return out_buf.getvalue()

class App:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title('PDF压缩工具')
        self.win.geometry('600x500')
        self.files = []
        
        tk.Label(self.win, text='PDF压缩工具', font=('Microsoft YaHei',16)).pack(pady=10)
        
        frame = tk.Frame(self.win)
        frame.pack(pady=5)
        tk.Button(frame, text='选择文件', command=self.pick_files, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text='选择文件夹', command=self.pick_folder, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text='清空列表', command=self.clear, width=12).pack(side=tk.LEFT, padx=5)
        
        self.listbox = tk.Listbox(self.win, height=12)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cfg = tk.Frame(self.win)
        cfg.pack(pady=5)
        tk.Label(cfg, text='质量:').pack(side=tk.LEFT)
        self.quality = tk.Scale(cfg, from_=20, to=80, orient=tk.HORIZONTAL, length=200)
        self.quality.set(45)
        self.quality.pack(side=tk.LEFT, padx=5)
        tk.Label(cfg, text='DPI:').pack(side=tk.LEFT, padx=(10,0))
        self.dpi_var = tk.StringVar(value='80')
        tk.Spinbox(cfg, from_=40, to=200, textvariable=self.dpi_var, width=6).pack(side=tk.LEFT, padx=5)
        
        tk.Button(self.win, text='开始压缩', command=self.start, bg='#722ed1', fg='white',
                  font=('Microsoft YaHei',14), height=2).pack(pady=10, fill=tk.X, padx=40)
        
        self.status = tk.Label(self.win, text='就绪', fg='#888')
        self.status.pack()
        
    def pick_files(self):
        fps = filedialog.askopenfilenames(title='选择PDF文件', filetypes=[('PDF','*.pdf')])
        for fp in fps:
            if fp not in self.files:
                self.files.append(fp)
        self.refresh()
    
    def pick_folder(self):
        folder = filedialog.askdirectory(title='选择文件夹')
        if not folder:
            return
        for root, dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith('.pdf'):
                    fp = os.path.join(root, f)
                    if fp not in self.files:
                        self.files.append(fp)
        self.refresh()
    
    def clear(self):
        self.files = []
        self.refresh()
    
    def refresh(self):
        self.listbox.delete(0, tk.END)
        for fp in self.files:
            sz = os.path.getsize(fp)
            name = os.path.basename(fp)
            self.listbox.insert(tk.END, '%s [%.1fMB]' % (name, sz/1024/1024))
        self.status.config(text='共 %d 个文件' % len(self.files))
    
    def start(self):
        if not self.files:
            messagebox.showwarning('提示', '请先选择PDF文件')
            return
        q = self.quality.get()
        dpi = int(self.dpi_var.get())
        
        ok = 0
        fail = 0
        for fp in self.files:
            name = os.path.basename(fp)
            old = os.path.getsize(fp)
            self.status.config(text='压缩中: %s' % name)
            self.win.update()
            try:
                data = compress_pdf(fp, dpi, q)
                if data and len(data) < old:
                    base, ext = os.path.splitext(fp)
                    out = base + '_压缩' + ext
                    with open(out, 'wb') as f:
                        f.write(data)
                    new = os.path.getsize(out)
                    pct = (1 - new/old) * 100
                    print('OK: %s %.1fMB -> %.1fMB (%.0f%%缩减)' % (name, old/1024/1024, new/1024/1024, pct))
                    ok += 1
                else:
                    print('SKIP: %s 压缩后未变小' % name)
                    fail += 1
            except Exception as e:
                print('FAIL: %s - %s' % (name, str(e)[:60]))
                fail += 1
        
        msg = '完成！成功 %d 个，失败 %d 个' % (ok, fail)
        self.status.config(text=msg)
        messagebox.showinfo('完成', msg + '\n压缩文件保存在原目录，文件名后缀 _压缩.pdf')
    
    def run(self):
        self.win.mainloop()

if __name__ == '__main__':
    App().run()
