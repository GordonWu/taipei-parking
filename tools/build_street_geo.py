#!/usr/bin/env python3
"""把停管處「臺北市路邊停車格位」SHP 壓成網頁用的 street_geo.json。

即時檔 TCMSV_roadquery.xml 只有路段代碼(roadSegID)沒有座標;SHP 的 rdcode 就是同一個代碼,
一筆 = 一個格位多邊形。這支腳本:
  1. 讀 SHP(TWD97 TM2),每個格位取多邊形中心點,轉 WGS84。
  2. 依 rdcode 分組。SHP 有 9 萬多格 rdcode 是空的,改用路名(roadname)對:
     路名 -> rdcode 的對照先從有 rdcode 的格位學,再用即時 XML 的 roadSegName(去掉前綴代碼)補。
  3. 只保留汽車類格位(pktype 見 CAR_TYPES),機車格不畫。
     路段中心 = 格位中心平均;格位座標存成相對中心的 1e-5 度整數位移(≈1 公尺),省空間。
  4. 行政區取該路段最多格位的 area_name。

用法:
  python3 tools/build_street_geo.py <解壓後的 shp 路徑(不含副檔名)> [--xml TCMSV_roadquery.xml] [輸出路徑]
預設輸出到 repo 根目錄 street_geo.json。SHP 每月更新一次,重跑一次 commit 即可。
需要 pyshp:pip install pyshp
"""
import collections
import datetime
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import shapefile  # pyshp

# pktype 代碼是從 pktype1 文字反推的(停管處沒文件):01 小型車、03 身障(汽)、05 警車/計程車、07 貨車裝卸、
# 08 計程車、09/10 限時/時段停車、15 停車彎、22 汽機車彈性共用、121 小型車、70 裝卸。其餘多是機車/機慢車區。
CAR_TYPES = {'01', '03', '05', '07', '08', '09', '10', '15', '22', '121', '70', '47'}
CLEAN = re.compile(r'^[0-9A-Z]{7}\(\d+\)\s*')


def tw97_to_wgs84(x, y):
    a, f, k0, dx, lon0 = 6378137.0, 1 / 298.257222101, 0.9999, 250000.0, math.radians(121.0)
    b = a * (1 - f)
    e2 = (a * a - b * b) / (a * a)
    e2p = (a * a - b * b) / (b * b)
    x -= dx
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    j1 = 3 * e1 / 2 - 27 * e1 ** 3 / 32
    j2 = 21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32
    j3 = 151 * e1 ** 3 / 96
    j4 = 1097 * e1 ** 4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    c1 = e2p * math.cos(fp) ** 2
    t1 = math.tan(fp) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(fp) ** 2) ** 1.5
    n1 = a / math.sqrt(1 - e2 * math.sin(fp) ** 2)
    d = x / (n1 * k0)
    q1 = n1 * math.tan(fp) / r1
    q2 = d * d / 2
    q3 = (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * e2p) * d ** 4 / 24
    q4 = (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 3 * c1 ** 2 - 252 * e2p) * d ** 6 / 720
    lat = fp - q1 * (q2 - q3 + q4)
    q5 = d
    q6 = (1 + 2 * t1 + c1) * d ** 3 / 6
    q7 = (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * e2p + 24 * t1 ** 2) * d ** 5 / 120
    lon = lon0 + (q5 - q6 + q7) / math.cos(fp)
    return math.degrees(lat), math.degrees(lon)


def main():
    args = [a for a in sys.argv[1:]]
    xml_path = None
    if '--xml' in args:
        i = args.index('--xml')
        xml_path = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        sys.exit(1)
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'street_geo.json')

    # 路名 -> rdcode(來自即時 XML 的 roadSegName)
    name2rd = {}
    if xml_path:
        for s in ET.parse(xml_path).getroot().findall('ROAD'):
            nm = CLEAN.sub('', s.findtext('roadSegName') or '').strip()
            rd = (s.findtext('roadSegID') or '').strip()
            if nm and rd and nm not in name2rd:
                name2rd[nm] = rd

    sf = shapefile.Reader(src, encoding='utf-8')
    names = [f[0] for f in sf.fields[1:]]
    ix = {n: i for i, n in enumerate(names)}

    # 第一遍:有 rdcode 的格位直接分組,並學 SHP 自己的路名 -> rdcode
    rows = []          # (rd or '', roadname, pktype, area, lat, lng)
    shp_name2rd = collections.defaultdict(collections.Counter)
    total = 0
    for rec, shp in zip(sf.iterRecords(), sf.iterShapes()):
        total += 1
        if not shp.points:
            continue
        rd = str(rec[ix['rdcode']]).strip()
        rn = str(rec[ix['roadname']]).strip()
        pt = str(rec[ix['pktype']]).strip()
        if pt not in CAR_TYPES and not rd:
            continue   # 沒 rdcode 的機車格不靠路名掛(會掛錯);有 rdcode 的留著當備援
        pts = shp.points
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        lat, lng = tw97_to_wgs84(cx, cy)
        rows.append((rd, rn, pt, str(rec[ix['area_name']]).strip(), lat, lng))
        if rd and rn:
            shp_name2rd[rn][rd] += 1

    # 第二遍:沒 rdcode 的格位用路名對(SHP 自己的對照優先,其次 XML 名稱)
    groups = collections.defaultdict(list)
    areas = collections.defaultdict(collections.Counter)
    rnames = collections.defaultdict(collections.Counter)
    attached = 0
    for rd, rn, pt, area, lat, lng in rows:
        if not rd:
            if rn in shp_name2rd and len(shp_name2rd[rn]) == 1:
                rd = next(iter(shp_name2rd[rn]))
            elif rn in name2rd:
                rd = name2rd[rn]
            else:
                continue
            attached += 1
        groups[rd].append((lat, lng, pt))
        areas[rd][area] += 1
        if rn:
            rnames[rd][CLEAN.sub('', rn).strip()] += 1

    segs = {}
    ncell = 0
    for rd, cells in groups.items():
        # 汽車類優先;整段都沒汽車格(例如純機車路段)才用全部
        car = [c for c in cells if c[2] in CAR_TYPES]
        cells = car or cells
        main = [c for c in cells if c[2] in ('01', '22')] or cells
        clat = sum(c[0] for c in main) / len(main)
        clng = sum(c[1] for c in main) / len(main)
        rel = [[round((lat - clat) * 1e5), round((lng - clng) * 1e5)] for lat, lng, _ in cells]
        ncell += len(rel)
        seg = {'c': [round(clat, 6), round(clng, 6)], 'a': areas[rd].most_common(1)[0][0], 'n': len(cells), 'p': rel}
        if rnames[rd]:
            seg['nm'] = rnames[rd].most_common(1)[0][0]
        if not car:
            seg['m'] = 1   # 只有機車格
        segs[rd] = seg

    doc = {
        'built': datetime.date.today().isoformat(),
        'source': os.path.basename(src),
        'note': 'c=路段中心[lat,lng]; a=行政區; nm=SHP路名(即時檔沒這段時當名稱用); n=汽車類格位數(含靠路名掛上的); m=1 表示只有機車格; p=各格位相對中心的位移(1e-5度整數)',
        'segs': segs,
    }
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(out)
    print(f'SHP 記錄 {total:,} 筆;汽車類格位 {len(rows):,} 格,其中靠路名掛上 {attached:,} 格;'
          f'路段 {len(segs):,} 條、格位 {ncell:,} 格 -> {out} ({size/1024:.0f} KB)')


if __name__ == '__main__':
    main()
