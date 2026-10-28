# 台北找車位

單一 HTML 檔的靜態網頁，直接讀臺北市停管處的開放資料，顯示即時剩餘車位、費率與導航。
沒有後端、沒有建置步驟，`index.html` 就是整個網站。

## 資料來源

臺北市資料大平臺「臺北市停車場資訊」
<https://data.taipei/dataset/detail?id=d5c0656b-5250-4179-a491-c94daa56ef2c>

| 檔案 | 內容 | 大小 | 更新 |
|---|---|---|---|
| `TCMSV_alldesc.xml` | 1,778 個停車場的靜態資料（名稱、地址、費率、總格數、TWD97 座標） | 4 MB | 每月 |
| `TCMSV_allavailable.xml` | 1,227 個有即時資料的停車場剩餘車位、充電槍狀態 | 0.7 MB | **每分鐘** |

兩個檔案都放在 Azure Blob 上且開放 CORS（`Access-Control-Allow-Origin: *`），所以瀏覽器可以直接抓，不需要代理伺服器。

網頁行為：
- 靜態清單第一次下載後存在瀏覽器 `localStorage`（約 1.5 MB），24 小時內不再重抓。
- 即時檔每 60 秒自動重抓（頁面在前景時），畫面上方顯示停管處的資料時間與幾分鐘前。超過 10 分鐘沒更新會標黃色警告。
- 座標由 TWD97 TM2 在瀏覽器內換算成 WGS84。

## 怎麼開

### 本機
```bash
cd taipei_parking
python3 -m http.server 8765
# 瀏覽器開 http://localhost:8765
```
直接雙擊 `index.html`（file://）也能看，但 Chrome 在 file:// 下不給定位權限，「定位到我」會失敗，改用地圖中心找附近即可。

### 放上網（手機要用就選一個）
- **GitHub Pages**：把這個資料夾推上 repo，Settings → Pages → 選 branch 根目錄。
- **Firebase Hosting**：`firebase init hosting`，public 目錄指到這裡，`firebase deploy`。
- **Cloudflare Pages / Netlify**：拖資料夾上去就好。

都是 https，定位才會有效。手機上「加入主畫面」就像 App 一樣用。

## 功能
- 車種切換：小型車 / 機車 / 充電 / 大重機 / 大客車
- 行政區篩選、關鍵字搜尋（名稱或地址）
- 只看有空位、只看有即時資料、只看收藏
- 排序：距離（你的位置或地圖中心）/ 空位數
- 地圖標記顏色：綠＝有車位、黃＝剩不多（≤3 格或 <10%）、紅＝已滿、灰＝無即時資料
- 詳細頁：各車種剩餘/總數、身障與婦幼格、充電槍逐支狀態、費率全文、營業時間、電話、Google / Apple 導航
- 深色模式跟隨系統（地圖底圖也會換）

## 已知限制
- 「無即時資料」的 412 個停車場（多是機關學校），只能看到總格數與費率。
- 費率是停管處的文字描述，網頁只從中抓第一個「N 元/時」當清單上的簡短顯示，實際以詳細頁全文為準。
- 底圖用內政部國土測繪中心「臺灣通用電子地圖」WMTS（免金鑰、開放 CORS）。深色模式是同一套圖磚加 CSS 濾鏡反轉。
  不用 OpenStreetMap 公共圖磚是因為它會對不符合 tile usage policy 的網頁回 403「Access blocked」；CARTO 深色圖磚則已改為需要 API key。
