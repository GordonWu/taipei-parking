#!/usr/bin/env python3
"""把停管處「臺北市路邊停車格位」SHP 壓成網頁用的 street_geo.json。

即時檔 TCMSV_roadquery.xml 只有路段代碼(roadSegID)沒有座標;SHP 的 rdcode 就是同一個代碼,
一筆 = 一個格位多邊形。這支腳本:
  1. 讀 SHP(TWD97 TM2),每個格位取多邊形中心點,轉 WGS84。
  2. 依 rdcode 分組:路段中心 = 格位中心平均;格位座標存成相對中心的 1e-5 度整數位移(≈1 公尺),省空間。
  3. 行政區取該路段最多格位的 area_name。

用法:
  python3 tools/build_street_geo.py <解壓後的 shp 路徑(不含副檔名)> [輸出路徑]
預設輸出到 repo 根目錄 street_geo.json。SHP 每月更新一次,重跑一次 commit 即可。
需要 pyshp:pip install pyshp
"""
import collections
import datetime
import json
import math
import os
import sys

import shapefile  # pyshp


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
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'street_geo.json')

    sf = shapefile.Reader(src, encoding='utf-8')
    names = [f[0] for f in sf.fields[1:]]
    ix = {n: i for i, n in enumerate(names)}
    groups = collections.defaultdict(list)   # rdcode -> [(lat, lng, pktype)]
    areas = collections.defaultdict(collections.Counter)
    roads = collections.defaultdict(collections.Counter)
    total = 0
    for rec, shp in zip(sf.iterRecords(), sf.iterShapes()):
        total += 1
        rd = str(rec[ix['rdcode']]).strip()
        if not rd or not shp.points:
            continue
        pts = shp.points
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        lat, lng = tw97_to_wgs84(cx, cy)
        groups[rd].append((lat, lng, str(rec[ix['pktype']]).strip()))
        areas[rd][str(rec[ix['area_name']]).strip()] += 1
        roads[rd][str(rec[ix['roadname']]).strip()] += 1

    segs = {}
    ncell = 0
    for rd, cells in groups.items():
        # 中心點優先用小型車格(01)與汽機車共用格(22),沒有才用全部
        car = [c for c in cells if c[2] in ('01', '22')] or cells
        clat = sum(c[0] for c in car) / len(car)
        clng = sum(c[1] for c in car) / len(car)
        rel = []
        for lat, lng, _ in cells:
            rel.append([round((lat - clat) * 1e5), round((lng - clng) * 1e5)])
        ncell += len(rel)
        area = areas[rd].most_common(1)[0][0]
        segs[rd] = {'c': [round(clat, 6), round(clng, 6)], 'a': area, 'n': len(cells), 'p': rel}

    doc = {
        'built': datetime.date.today().isoformat(),
        'source': os.path.basename(src),
        'note': 'c=路段中心[lat,lng]; a=行政區; n=SHP格位數; p=各格位相對中心的位移(1e-5度整數)',
        'segs': segs,
    }
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(out)
    print(f'SHP 記錄 {total:,} 筆,有 rdcode 的格位 {ncell:,} 格,路段 {len(segs):,} 條 -> {out} ({size/1024:.0f} KB)')


if __name__ == '__main__':
    main()
