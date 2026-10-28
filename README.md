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
| `TCMSV_roadquery.xml` | **路邊停車格**：2,341 條收費路段的剩餘格數，其中約 2,000 段附每格感測狀態（2.6 萬格） | 7.7 MB | **每分鐘** |

路邊檔來自同一個停管處的另一個資料集「[臺北市路邊停車格位使用情形](https://data.taipei/dataset/detail?id=434638ca-8770-42c1-940d-0386a74f6eb9)」（平臺上標「每年更新」是指格位清冊，檔案本身是即時的）。
路邊檔只有路段代碼沒有座標，座標來自「[臺北市路邊停車格位](https://data.taipei/dataset/detail?id=5a911ea5-1694-4301-808e-e1780d971611)」SHP 圖層，用 `rdcode` 對 `roadSegID`，由 `tools/build_street_geo.py` 壓成 `street_geo.json`（1.2 MB，gzip 後約 390 KB，切到路邊模式才載）。

三個檔案都放在 Azure Blob 上且開放 CORS（`Access-Control-Allow-Origin: *`），所以瀏覽器可以直接抓，不需要代理伺服器。

網頁行為：
- 靜態清單第一次下載後存在瀏覽器 `localStorage`（約 1.5 MB），24 小時內不再重抓。
- 停車場即時檔每 60 秒自動重抓；路邊檔 7.7 MB 沒壓縮，所以每 3 分鐘才抓一次（都只在頁面在前景時）。畫面上方顯示停管處的資料時間與幾分鐘前，超過 10 分鐘沒更新會標黃色警告。
- 座標由 TWD97 TM2 在瀏覽器內（停車場）或建檔時（路邊格）換算成 WGS84。

路邊格的資料解讀（停管處沒有公開欄位文件，以下是用 2026-10-28 的資料與路段剩餘數交叉比對推出來的）：
- `roadSegAvail` 是官方的路段剩餘格數，`-99` 表示沒資料；網頁以它為準，沒有時才用感測格數推算。
- `cellStatus`：`1` 有車、`2` 空位、其他視為異常。感測格數常少於路段總格數（只有部分格位埋地磁）。
- `psId`（感測器編號）對不上 SHP 的格位編號，所以地圖放大後只畫每一格的位置，顏色跟路段一致，**不會標出是哪一格空**。
- SHP 有 9 萬多格沒填 `rdcode`，建檔時改用路名對到路段（先用 SHP 自己有代碼的同名格位，再用即時檔的路段名）；只掛汽車類格位（小型車、身障、裝卸、彈性共用等），機車格不掛以免掛錯。
- 路邊模式預設**不**過濾「只看有空位」，已滿路段以紅色 0/N 顯示，才不會以為那條路不存在。

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

## 更新路邊格位座標（每月一次就夠）
```bash
pip install pyshp
# 從 data.taipei 下載「臺北市路邊停車格位」SHP 並解壓，然後：
curl -sL https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_roadquery.xml -o /tmp/roadquery.xml
python3 tools/build_street_geo.py /path/to/park01_YYYYMMDDHHMM --xml /tmp/roadquery.xml
git add street_geo.json && git commit -m "更新路邊格位座標" && git push
```

## 功能
- 兩種模式：**路邊停車格**（路段剩餘、每格感測狀態、收費與時段）/ **停車場**
- 車種切換（停車場模式）：小型車 / 機車 / 充電 / 大重機 / 大客車
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
