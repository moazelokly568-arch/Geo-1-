import math
from typing import Any, Dict, List
from pyproj import Transformer


def dms_to_decimal(deg: int, minutes: int, seconds: float, hemi: str = "N") -> float:
    sign = -1 if hemi.upper() in {"S", "W"} or deg < 0 else 1
    val = abs(deg) + (minutes / 60.0) + (seconds / 3600.0)
    return round(sign * val, 8)


def decimal_to_dms(decimal_deg: float, is_lat: bool = True) -> Dict[str, Any]:
    hemi = ("N" if decimal_deg >= 0 else "S") if is_lat else ("E" if decimal_deg >= 0 else "W")
    abs_val = abs(decimal_deg)
    deg = int(abs_val)
    rem = (abs_val - deg) * 60.0
    minutes = int(rem)
    seconds = round((rem - minutes) * 60.0, 4)
    return {"deg": deg, "min": minutes, "sec": seconds, "hemisphere": hemi, "formatted": f"{deg}° {minutes}' {seconds}\" {hemi}"}


def latlon_to_utm(lat: float, lon: float) -> Dict[str, Any]:
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 + zone) if lat >= 0 else (32700 + zone)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    easting, northing = transformer.transform(lon, lat)
    return {
        "easting": round(easting, 4),
        "northing": round(northing, 4),
        "zone": zone,
        "hemisphere": "N" if lat >= 0 else "S",
        "epsg": f"EPSG:{epsg}",
    }


def solve_differential_leveling(initial_bm: float, stations: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_rl = initial_bm
    prev_reading = None
    sum_bs = 0.0
    sum_fs = 0.0
    sum_rise = 0.0
    sum_fall = 0.0
    table = []

    for idx, st in enumerate(stations):
        bs = st.get("bs")
        inter = st.get("is")
        fs = st.get("fs")
        rise = 0.0
        fall = 0.0

        if idx == 0:
            if bs is None:
                raise ValueError("يجب أن تبدأ النقطة الأولى بقراءة مؤخرة (BS) على الروبير.")
            sum_bs += bs
            prev_reading = bs
        else:
            curr_sight = fs if fs is not None else inter
            if curr_sight is None:
                raise ValueError(f"النقطة رقم {idx+1} لا تحتوي على قراءة متوسطة (IS) أو مقدمة (FS).")
            diff = prev_reading - curr_sight
            if diff >= 0:
                rise = round(diff, 4)
                sum_rise += rise
            else:
                fall = round(abs(diff), 4)
                sum_fall += fall
            current_rl = round(current_rl + diff, 4)

            if fs is not None:
                sum_fs += fs
            if bs is not None:
                sum_bs += bs
                prev_reading = bs
            else:
                prev_reading = curr_sight

        table.append({
            "station": st.get("name", f"ST-{idx+1}"),
            "bs": bs,
            "is": inter,
            "fs": fs,
            "rise": rise,
            "fall": fall,
            "rl": current_rl,
        })

    check_bs_fs = round(sum_bs - sum_fs, 4)
    check_rise_fall = round(sum_rise - sum_fall, 4)
    check_rl = round(current_rl - initial_bm, 4)
    verified = abs(check_bs_fs - check_rl) < 1e-3 and abs(check_rise_fall - check_rl) < 1e-3

    return {
        "table": table,
        "arithmetic_check": {
            "sum_bs_minus_sum_fs": check_bs_fs,
            "sum_rise_minus_sum_fall": check_rise_fall,
            "last_rl_minus_first_rl": check_rl,
            "is_verified": verified,
        },
    }


def adjust_closed_traverse_bowditch(
    start_e: float,
    start_n: float,
    legs: List[Dict[str, float]],
) -> Dict[str, Any]:
    total_length = sum(leg["length"] for leg in legs)
    if total_length <= 0:
        raise ValueError("إجمالي أطوال أضلاع الترافيرس يجب أن يكون أكبر من الصفر.")

    raw_legs = []
    sum_de = 0.0
    sum_dn = 0.0
    for leg in legs:
        rad = math.radians(leg["azimuth_deg"])
        de = leg["length"] * math.sin(rad)
        dn = leg["length"] * math.cos(rad)
        sum_de += de
        sum_dn += dn
        raw_legs.append({**leg, "de": de, "dn": dn})

    linear_misclosure = math.hypot(sum_de, sum_dn)
    relative_precision = int(round(total_length / linear_misclosure)) if linear_misclosure > 0 else 999999

    curr_e, curr_n = start_e, start_n
    adjusted = []
    for leg in raw_legs:
        corr_e = -sum_de * (leg["length"] / total_length)
        corr_n = -sum_dn * (leg["length"] / total_length)
        adj_de = leg["de"] + corr_e
        adj_dn = leg["dn"] + corr_n
        curr_e += adj_de
        curr_n += adj_dn
        adjusted.append({
            "leg": leg.get("name", ""),
            "length_m": round(leg["length"], 3),
            "azimuth_deg": leg["azimuth_deg"],
            "corr_e": round(corr_e, 4),
            "corr_n": round(corr_n, 4),
            "adjusted_e": round(curr_e, 4),
            "adjusted_n": round(curr_n, 4),
        })

    return {
        "total_length_m": round(total_length, 3),
        "misclosure_e_m": round(sum_de, 4),
        "misclosure_n_m": round(sum_dn, 4),
        "linear_misclosure_m": round(linear_misclosure, 4),
        "relative_precision": f"1 : {relative_precision:,}",
        "adjusted_stations": adjusted,
    }
