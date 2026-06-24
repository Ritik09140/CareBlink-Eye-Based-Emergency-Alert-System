# 🚀 CareBlink - VS Code Setup & Run Guide

मैंने VS Code के लिए **Launch Configuration (`launch.json`)** बना दिया है। इससे आप दोनों Scripts (Flask Web Server और Eye Blink Detector) को VS Code के अंदर से एक-क्लिक में run कर सकते हैं। 

नीचे दिए गए steps को follow करें:

---

## 🛠️ Step 1: Open Folder in VS Code (VS Code में फ़ोल्डर खोलें)
1. **VS Code** को open करें।
2. **File > Open Folder...** पर जाएं।
3. इस फ़ोल्डर को select करें: `Z:\CareBlink – Smart Eye-Based Patient Emergency Alert System`

---

## 🐍 Step 2: Install Python & Extensions (Python और Extensions इंस्टॉल करें)
1. सुनिश्चित करें कि आपके computer में **Python** (version 3.8 या उससे नया) installed है।
2. VS Code में **Extensions** tab (left side window में 5वें icon पर click करें या `Ctrl+Shift+X` दबाएं)।
3. Search bar में **Python** search करें और Microsoft द्वारा develop किए गए **Python** extension को install करें।

---

## 📦 Step 3: Install Dependencies (Requirements इंस्टॉल करें)
1. VS Code में **Terminal** open करें (`Ctrl + ~` दबाएं या ऊपर menu में **Terminal > New Terminal** पर click करें)।
2. Terminal में नीचे दिया गया command run करें:
   ```bash
   pip install -r requirements.txt
   ```
   *यह project के लिए ज़रूरी libraries (Flask, OpenCV, MediaPipe, आदि) install कर देगा।*

---

## 🏃 Step 4: Run the Application (VS Code से Run करें)
मैंने `.vscode/launch.json` configuration बना दिया है, जिससे आपको manual command prompt windows open करने की आवश्यकता नहीं होगी।

1. Left Sidebar में **Run & Debug** icon पर click करें (या `Ctrl+Shift+D` दबाएं)।
2. Dropdown menu (top-left sidebar) में आपको 3 options दिखाई देंगे:
   - **`Run Both (Flask + Detector)`** (Recommended: यह एक साथ Web Server और Eye Detector दोनों launch कर देगा)
   - **`Flask Server (app.py)`** (केवल Doctor's web portal run करने के लिए)
   - **`Eye Blink Detector (detector.py)`** (केवल Webcam processing run करने के लिए)
3. **`Run Both (Flask + Detector)`** select करें और उसके बगल में बने **Play (Green Triangle)** button पर click करें या `F5` दबाएं।

---

## 🌐 Step 5: Test the System (सिस्टम टेस्ट करें)
1. **Web Dashboard:**
   - Web Server start होने के बाद, browser खोलें और **`http://localhost:5000`** पर जाएं।
   - **Login Details:**
     - **Username/Mobile:** `1234567890` (या `doctor`)
     - **Password:** `password123`
2. **Camera Window:**
   - Detector open होने पर camera feed window open होगा।
   - कैमरे के सामने आकर **5 बार तेजी से (5 seconds के अंदर) आँखें झपकाएं (Blink)**।
   - Web browser dashboard पर **Red alert light** blink होने लगेगी और sound alarm play होगा!
3. **Dismiss Alert:** Dashboard पर **"Dismiss & Reset Alarm"** click करें।

---

### 💡 Troubleshooting (अगर कोई समस्या आती है):
* **Webcam error:** सुनिश्चित करें कि कोई दूसरा app (जैसे Zoom, Teams, Chrome) आपके कैमरे का उपयोग नहीं कर रहा है।
* **Database error:** MySQL running नहीं होने पर App automatically local SQLite (`careblink.db`) पर shift हो जाता है, इसलिए database config की चिंता करने की ज़रूरत नहीं है।
