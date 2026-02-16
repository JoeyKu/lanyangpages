// 設定區域：在此新增花邊圖片路徑
const CORNER_IMAGES = [
    'assets/corner/corner_01.png',
];

let pyodide;
const generateBtn = document.getElementById('generate-btn');
const btnText = document.getElementById('btn-text');
const btnSpinner = document.getElementById('btn-spinner');
const statusContainer = document.getElementById('status-container');
const statusMsg = document.getElementById('status-msg');
const progressBar = document.getElementById('progress-bar');
const excelInput = document.getElementById('excel-file');
const eventNameInput = document.getElementById('event-name');
const cornerOptionsContainer = document.getElementById('corner-options');

// 載入儲存的活動名稱
const savedEventName = localStorage.getItem('blia_event_name');
if (savedEventName) {
    eventNameInput.value = savedEventName;
}

// 監聽輸入並儲存到 LocalStorage
eventNameInput.addEventListener('input', (e) => {
    localStorage.setItem('blia_event_name', e.target.value);
});

// 動態產生花邊選項
function renderCornerOptions() {
    cornerOptionsContainer.innerHTML = CORNER_IMAGES.map((path, index) => {
        const id = `corner_${index}`;
        const name = path.split('/').pop().split('.')[0];
        return `
            <div class="corner-item">
                <input type="radio" name="corner" id="${id}" value="${path}" ${index === 0 ? 'checked' : ''}>
                <label for="${id}" class="text-center">
                    <img src="${path}" alt="${name}" class="img-thumbnail d-block mx-auto mb-1" style="width: 80px; height: 80px;">
                    <span class="small">${name}</span>
                </label>
            </div>
        `;
    }).join('');
}

async function updateStatus(message, progress) {
    statusMsg.innerText = message;
    progressBar.style.width = progress + '%';
    console.log(`[Status] ${message} (${progress}%)`);
}

async function initPyodide() {
    try {
        statusContainer.classList.remove('d-none');
        await updateStatus('正在載入 Pyodide 核心...', 10);
        pyodide = await loadPyodide();
        await updateStatus('正在安裝必要套件 (pandas, openpyxl, reportlab)...', 30);
        await pyodide.loadPackage(['micropip']);
        const micropip = pyodide.pyimport('micropip');
        await micropip.install(['pandas', 'openpyxl', 'reportlab']);
        await updateStatus('載入字體檔...', 70);
        const fontRes = await fetch('assets/fonts/arial_unicode.ttf');
        const fontData = await fontRes.arrayBuffer();
        pyodide.FS.writeFile('/ArialUnicode.ttf', new Uint8Array(fontData));
        await updateStatus('系統就緒', 100);
        generateBtn.disabled = false;
        btnText.innerText = '產生獎項卡片';
        setTimeout(() => { statusContainer.classList.add('d-none'); }, 2000);
    } catch (error) {
        console.error(error);
        statusMsg.innerHTML = `<span class="text-danger">初始化失敗: ${error.message}</span>`;
        progressBar.classList.add('bg-danger');
    }
}

async function generatePDF() {
    if (!excelInput.files[0]) {
        alert('請先選擇一個 Excel 檔案');
        return;
    }

    const excelFile = excelInput.files[0];
    const cornerPath = document.querySelector('input[name="corner"]:checked').value;
    const layout = document.querySelector('input[name="layout"]:checked').value;
    const eventName = eventNameInput.value || "獎項卡片";

    generateBtn.disabled = true;
    btnSpinner.classList.remove('d-none');
    btnText.innerText = '正在產生 PDF...';
    statusContainer.classList.remove('d-none');
    await updateStatus('讀取檔案中...', 20);

    try {
        const excelData = await excelFile.arrayBuffer();
        pyodide.FS.writeFile('/data.xlsx', new Uint8Array(excelData));
        const cornerRes = await fetch(cornerPath);
        const cornerData = await cornerRes.arrayBuffer();
        pyodide.FS.writeFile('/corner.png', new Uint8Array(cornerData));

        await updateStatus('執行繪圖邏輯 (ReportLab)...', 60);

        const pythonCode = `
    import pandas as pd
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    
    FONT_PATH = "/ArialUnicode.ttf"
    FONT_NAME = "ArialUnicode"
    CORNER_IMAGE = "/corner.png"
    OUTPUT_PDF = "/output.pdf"
    EXCEL_FILE = "/data.xlsx"
    LAYOUT = "${layout}"
    EVENT_NAME = """${eventName}"""
    
    pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    
    def draw_centred_text_auto_size(c, text, center_x, y, max_w, default_size, min_size=8):
        size = default_size
        while size >= min_size:
            c.setFont(FONT_NAME, size)
            tw = c.stringWidth(text, FONT_NAME, size)
            if tw <= max_w:
                break
            size -= 1
        c.drawCentredString(center_x, y, text)
    
    def draw_label(c, x, y, w, h, row):
        c.setLineWidth(1)
        c.setStrokeColorRGB(0, 0, 0) # Black for border
        padding = 10
        lx, ly, lw, lh = x + padding, y + padding, w - padding*2, h - padding*2
        c.rect(lx, ly, lw, lh)

        def place_corner(cx, cy, deg):
            c.saveState()
            c.translate(cx, cy)
            c.rotate(deg)
            if os.path.exists(CORNER_IMAGE):
                # Reduced corner size for better text space
                img_size = min(w, h) * 0.2
                if img_size > 60: img_size = 60
                c.drawImage(CORNER_IMAGE, 0, -img_size, width=img_size, height=img_size, mask='auto')
            c.restoreState()

        place_corner(lx + 5, ly + lh - 5, 0)
        place_corner(lx + lw - 5, ly + lh - 5, -90)
        place_corner(lx + 5, ly + 5, 90)
        place_corner(lx + lw - 5, ly + 5, 180)

        center_x = lx + lw / 2
        text_max_w = lw - 40 # Increased horizontal padding for text

        if LAYOUT == "3x2":
            # Adjust positions for 3x2 to avoid corners and look better
            # Title - Moved down more to avoid top corners
            draw_centred_text_auto_size(c, EVENT_NAME, center_x, ly + lh - 65, text_max_w, 11)
            # Prize and Number
            full_prize_text = f"{row['獎項']}{row['編號']}"
            draw_centred_text_auto_size(c, full_prize_text, center_x, ly + lh * 0.55, text_max_w, 52)
            # Unit Name
            unit_text = str(row['單位名稱'])
            draw_centred_text_auto_size(c, unit_text, center_x, ly + lh * 0.35, text_max_w, 24)
            # Name and Giver - Moved up to avoid bottom corners
            name_info = str(row['職稱姓名']) if pd.notna(row['職稱姓名']) and row['職稱姓名'] != "" else ""
            footer = f"{name_info} 敬贈".strip()
            draw_centred_text_auto_size(c, footer, center_x, ly + 65, text_max_w, 18)
        else:
            # Original 2x2 layout settings
            draw_centred_text_auto_size(c, EVENT_NAME, center_x, ly + lh - 40, text_max_w, 15)
            full_prize_text = f"{row['獎項']}{row['編號']}"
            draw_centred_text_auto_size(c, full_prize_text, center_x, ly + lh * 0.52, text_max_w, 75)
            unit_text = str(row['單位名稱'])
            draw_centred_text_auto_size(c, unit_text, center_x, ly + lh * 0.3, text_max_w, 36)
            name_info = str(row['職稱姓名']) if pd.notna(row['職稱姓名']) and row['職稱姓名'] != "" else ""
            footer = f"{name_info} 敬贈".strip()
            draw_centred_text_auto_size(c, footer, center_x, ly + lh * 0.15, text_max_w, 28)

    def main():
        df = pd.read_excel(EXCEL_FILE)
        pagesize = landscape(A4)
        width, height = pagesize
        c = canvas.Canvas(OUTPUT_PDF, pagesize=pagesize)

        if LAYOUT == "3x2":
            cols, rows = 3, 2
            # 8cm = 8 * 28.346 = 226.768 points
            label_w = 8 * 28.346
            label_h = height / rows
            # Center the 3 columns
            total_w = cols * label_w
            start_x = (width - total_w) / 2
        else: # 2x2
            cols, rows = 2, 2
            label_w = width / cols
            label_h = height / rows
            start_x = 0

        labels_per_page = cols * rows

        count = 0
        for _, row in df.iterrows():
            idx_in_page = count % labels_per_page
            col = idx_in_page % cols
            row_idx = idx_in_page // cols

            px = start_x + col * label_w
            py = height - (row_idx + 1) * label_h
            draw_label(c, px, py, label_w, label_h, row)

            count += 1
            if count % labels_per_page == 0:
                c.showPage()

        # Ensure the last page is finished if it wasn't full
        if count > 0 and count % labels_per_page != 0:
            c.showPage()

        c.save()

    main()
            `;

        await pyodide.runPythonAsync(pythonCode);
        await updateStatus('產生 PDF 中...', 90);
        const pdfData = pyodide.FS.readFile('/output.pdf');
        const blob = new Blob([pdfData], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);

        // 產生檔名：活動名稱_時間_佈局.pdf
        const now = new Date();
        const timestamp = now.getFullYear() +
            (now.getMonth() + 1).toString().padStart(2, '0') +
            now.getDate().toString().padStart(2, '0') + "_" +
            now.getHours().toString().padStart(2, '0') +
            now.getMinutes().toString().padStart(2, '0');

        const fileName = `${eventName}_${timestamp}_${layout}.pdf`;

        const a = document.createElement('a');
        a.href = url;
        a.download = fileName; document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        await updateStatus('完成！', 100);
        setTimeout(() => statusContainer.classList.add('d-none'), 3000);
    } catch (error) {
        console.error(error);
        alert('產生失敗: ' + error.message);
    } finally {
        generateBtn.disabled = false;
        btnSpinner.classList.add('d-none');
        btnText.innerText = '產生獎項卡片';
    }
}

generateBtn.addEventListener('click', generatePDF);
renderCornerOptions();
initPyodide();
