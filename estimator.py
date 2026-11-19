import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


# Curated Japanese & everyday meal dictionary:
# (keywords, canonical_name, kcal, protein_g, fat_g, carbs_g, category)
FOOD_DICTIONARY: List[Tuple[List[str], str, int, float, float, float, str]] = [
    # ご飯・おにぎり・丼もの
    (["白米", "ごはん", "ご飯", "ライス"], "ご飯（普通盛り・150g）", 234, 3.8, 0.5, 55.7, "主食"),
    (["玄米"], "玄米ご飯（150g）", 228, 4.2, 1.5, 51.3, "主食"),
    (["おにぎり", "おむすび", "鮭おにぎり", "梅おにぎり"], "おにぎり（1個）", 180, 4.0, 1.2, 38.0, "主食"),
    (["ツナマヨおにぎり", "ツナマヨ"], "ツナマヨおにぎり", 225, 5.2, 6.0, 37.5, "主食"),
    (["牛丼"], "牛丼（並盛）", 635, 19.5, 21.0, 90.0, "丼・麺"),
    (["豚丼"], "豚丼（並盛）", 680, 22.0, 22.5, 92.0, "丼・麺"),
    (["親子丼"], "親子丼", 620, 26.0, 15.0, 91.0, "丼・麺"),
    (["かつ丼", "カツ丼"], "カツ丼", 890, 28.0, 36.0, 108.0, "丼・麺"),
    (["天丼"], "天丼", 780, 18.0, 28.0, 108.0, "丼・麺"),
    (["海鮮丼", "刺身丼"], "海鮮丼", 560, 29.0, 8.5, 86.0, "丼・麺"),
    (["うな丼", "うな重", "鰻重"], "うな丼", 720, 24.0, 24.0, 96.0, "丼・麺"),
    (["チャーハン", "炒飯"], "チャーハン", 680, 15.0, 24.0, 96.0, "丼・麺"),
    (["オムライス"], "オムライス", 720, 19.0, 26.0, 98.0, "洋食"),
    (["カレーライス", "カレー"], "カレーライス", 760, 16.0, 22.0, 118.0, "洋食"),
    (["カツカレー"], "カツカレー", 1050, 28.0, 44.0, 130.0, "洋食"),
    (["ハヤシライス"], "ハヤシライス", 710, 15.0, 21.0, 110.0, "洋食"),
    (["寿司", "すし", "にぎり寿司"], "にぎり寿司（10貫）", 520, 24.0, 8.0, 84.0, "和食"),

    # 麺類
    (["ラーメン", "醤油ラーメン", "中華そば"], "醤油ラーメン", 480, 18.0, 12.0, 72.0, "丼・麺"),
    (["味噌ラーメン", "みそラーメン"], "味噌ラーメン", 580, 20.0, 18.0, 78.0, "丼・麺"),
    (["豚骨ラーメン", "とんこつラーメン"], "豚骨ラーメン", 620, 21.0, 24.0, 75.0, "丼・麺"),
    (["つけ麺"], "つけ麺（並）", 660, 23.0, 14.0, 105.0, "丼・麺"),
    (["ちゃんぽん"], "ちゃんぽん", 590, 24.0, 18.0, 78.0, "丼・麺"),
    (["うどん", "かけうどん", "きつねうどん"], "うどん（1杯）", 350, 10.0, 3.5, 68.0, "丼・麺"),
    (["天ぷらうどん"], "天ぷらうどん", 490, 14.0, 14.0, 75.0, "丼・麺"),
    (["そば", "蕎麦", "ざるそば", "かけそば"], "そば（1人前）", 320, 13.0, 2.5, 60.0, "丼・麺"),
    (["天ぷらそば"], "天ぷらそば", 470, 16.0, 13.0, 68.0, "丼・麺"),
    (["焼きそば", "焼そば"], "焼きそば", 540, 14.0, 20.0, 72.0, "丼・麺"),
    (["パスタ", "スパゲティ", "ミートソース"], "ミートソーススパゲティ", 620, 20.0, 18.0, 88.0, "洋食"),
    (["カルボナーラ"], "カルボナーラ", 780, 24.0, 38.0, 80.0, "洋食"),
    (["ペペロンチーノ"], "ペペロンチーノ", 550, 13.0, 19.0, 78.0, "洋食"),
    (["ナポリタン"], "ナポリタン", 610, 16.0, 19.0, 88.0, "洋食"),
    (["そうめん", "素麺"], "そうめん（1人前）", 330, 9.0, 1.5, 68.0, "丼・麺"),

    # パン・朝食
    (["食パン", "トースト", "バタートースト"], "バタートースト（6枚切り1枚）", 230, 5.5, 8.5, 32.0, "パン"),
    (["クロワッサン"], "クロワッサン（1個）", 210, 4.0, 12.0, 21.0, "パン"),
    (["サンドイッチ", "ミックスサンド"], "ミックスサンドイッチ", 340, 11.0, 15.0, 38.0, "パン"),
    (["たまごサンド", "卵サンド"], "たまごサンド", 360, 11.0, 19.0, 35.0, "パン"),
    (["あんぱん", "アンパン"], "あんぱん", 280, 7.0, 3.0, 56.0, "パン"),
    (["メロンパン"], "メロンパン", 380, 7.5, 12.0, 60.0, "パン"),
    (["カレーパン"], "カレーパン", 360, 7.5, 19.0, 39.0, "パン"),
    (["ベーグル"], "ベーグル（1個）", 250, 8.5, 1.5, 50.0, "パン"),
    (["オートミール"], "オートミール（40g＋牛乳）", 250, 9.5, 6.5, 38.0, "朝食"),
    (["シリアル", "グラノーラ", "フルーツグラノーラ"], "グラノーラ（50g＋牛乳）", 320, 8.5, 10.0, 48.0, "朝食"),
    (["目玉焼き"], "目玉焼き（1個）", 110, 7.0, 8.5, 0.5, "おかず"),
    (["ゆで卵", "ゆでたまご", "温泉卵"], "ゆで卵（1個）", 75, 6.5, 5.2, 0.2, "おかず"),
    (["卵焼き", "玉子焼き", "だし巻き卵"], "だし巻き卵（2切れ）", 140, 8.5, 9.5, 4.5, "おかず"),
    (["納豆"], "納豆（1パック）", 100, 8.3, 5.0, 6.1, "おかず"),
    (["味噌汁", "みそ汁"], "味噌汁（1杯）", 45, 2.5, 1.2, 5.5, "汁物"),
    (["豚汁", "とんじる"], "豚汁（1杯）", 150, 7.5, 7.5, 12.0, "汁物"),
    (["コーンスープ", "ポタージュ"], "コーンスープ", 130, 3.0, 5.0, 18.0, "汁物"),

    # 定食・主菜
    (["唐揚げ定食", "からあげ定食"], "唐揚げ定食", 850, 34.0, 34.0, 96.0, "定食"),
    (["唐揚げ", "からあげ", "鶏の唐揚げ"], "鶏の唐揚げ（4〜5個）", 420, 24.0, 26.0, 20.0, "おかず"),
    (["とんかつ定食", "トンカツ定食"], "とんかつ定食", 920, 32.0, 42.0, 98.0, "定食"),
    (["とんかつ", "トンカツ", "ロースカツ"], "とんかつ（単品）", 480, 22.0, 34.0, 20.0, "おかず"),
    (["生姜焼き定食", "しょうが焼き定食"], "豚の生姜焼き定食", 780, 28.0, 26.0, 98.0, "定食"),
    (["生姜焼き", "しょうが焼き"], "豚の生姜焼き（単品）", 380, 21.0, 24.0, 16.0, "おかず"),
    (["焼き魚定食", "焼魚定食", "サバ塩焼き定食", "鮭定食"], "焼き魚定食", 620, 29.0, 18.0, 80.0, "定食"),
    (["サバの塩焼き", "さば塩焼き", "焼きサバ"], "サバの塩焼き", 260, 18.0, 20.0, 0.5, "おかず"),
    (["鮭の塩焼き", "焼き鮭", "焼鮭"], "鮭の塩焼き", 150, 19.0, 7.0, 0.3, "おかず"),
    (["サバの味噌煮", "さば味噌"], "サバの味噌煮", 310, 18.0, 20.0, 13.0, "おかず"),
    (["ハンバーグ定食"], "ハンバーグ定食", 810, 28.0, 34.0, 92.0, "定食"),
    (["ハンバーグ"], "ハンバーグ（単品）", 420, 20.0, 28.0, 20.0, "おかず"),
    (["チキン南蛮"], "チキン南蛮", 580, 25.0, 38.0, 32.0, "おかず"),
    (["麻婆豆腐", "マーボー豆腐"], "麻婆豆腐", 360, 18.0, 24.0, 16.0, "おかず"),
    (["餃子", "ぎょうざ", "焼き餃子"], "焼き餃子（6個）", 320, 11.0, 16.0, 32.0, "おかず"),
    (["回鍋肉", "ホイコーロー"], "回鍋肉", 420, 16.0, 30.0, 18.0, "おかず"),
    (["青椒肉絲", "チンジャオロース"], "青椒肉絲", 340, 17.0, 22.0, 16.0, "おかず"),
    (["酢豚"], "酢豚", 430, 17.0, 24.0, 34.0, "おかず"),
    (["エビフライ"], "エビフライ（2本）", 310, 14.0, 18.0, 22.0, "おかず"),
    (["コロッケ"], "コロッケ（1個）", 190, 4.0, 10.0, 20.0, "おかず"),
    (["肉じゃが"], "肉じゃが", 240, 9.0, 8.0, 32.0, "おかず"),
    (["筑前煮"], "筑前煮", 190, 9.0, 6.0, 24.0, "おかず"),
    (["冷奴", "ひややっこ"], "冷奴（半丁）", 90, 7.5, 5.0, 3.0, "おかず"),
    (["刺身", "お刺身", "刺身盛り合わせ"], "刺身盛り合わせ", 180, 26.0, 6.0, 2.0, "おかず"),
    (["焼き鳥", "やきとり"], "焼き鳥（3本）", 260, 21.0, 16.0, 5.0, "おかず"),

    # サラダ・ヘルシー系
    (["サラダ", "グリーンサラダ", "野菜サラダ"], "野菜サラダ（ドレッシング付）", 95, 2.0, 5.5, 9.0, "サラダ"),
    (["シーザーサラダ"], "シーザーサラダ", 210, 7.0, 16.0, 9.0, "サラダ"),
    (["ポテトサラダ", "ポテサラ"], "ポテトサラダ", 180, 3.0, 10.0, 19.0, "サラダ"),
    (["サラダチキン"], "サラダチキン（1個）", 120, 24.0, 1.5, 1.0, "ヘルシー"),
    (["プロテイン"], "プロテインドリンク（1杯）", 110, 21.0, 1.5, 3.5, "ヘルシー"),
    (["豆腐バー"], "豆腐バー", 110, 10.0, 6.0, 3.0, "ヘルシー"),

    # ファストフード・弁当
    (["ハンバーガー"], "ハンバーガー", 260, 13.0, 9.5, 30.0, "ファストフード"),
    (["チーズバーガー"], "チーズバーガー", 310, 16.0, 13.5, 31.0, "ファストフード"),
    (["ビッグマック"], "ビッグマック", 525, 26.0, 28.0, 42.0, "ファストフード"),
    (["フライドポテト", "ポテト"], "フライドポテト（M）", 410, 5.0, 20.0, 52.0, "ファストフード"),
    (["ピザ", "マルゲリータ"], "ピザ（2〜3切れ）", 520, 20.0, 20.0, 62.0, "洋食"),
    (["幕の内弁当", "弁当", "お弁当"], "幕の内弁当", 720, 24.0, 20.0, 105.0, "弁当"),
    (["のり弁", "のり弁当"], "のり弁当", 760, 20.0, 26.0, 108.0, "弁当"),
    (["からあげ弁当", "唐揚げ弁当"], "唐揚げ弁当", 880, 28.0, 32.0, 114.0, "弁当"),
    (["おでん"], "おでん（5品）", 260, 16.0, 8.0, 28.0, "和食"),
    (["中華まん", "肉まん"], "肉まん（1個）", 230, 7.0, 7.5, 33.0, "軽食"),
    (["あんまん"], "あんまん（1個）", 260, 6.0, 3.0, 52.0, "軽食"),
    (["たこ焼き"], "たこ焼き（6個）", 320, 10.0, 12.0, 42.0, "軽食"),
    (["お好み焼き"], "お好み焼き（豚玉）", 550, 21.0, 24.0, 58.0, "和食"),

    # デザート・間食
    (["ヨーグルト"], "プレーンヨーグルト（100g）", 62, 3.6, 3.0, 4.9, "間食"),
    (["バナナ"], "バナナ（1本）", 90, 1.1, 0.2, 22.5, "果物"),
    (["りんご", "リンゴ"], "りんご（1/2個）", 75, 0.3, 0.2, 19.5, "果物"),
    (["ケーキ", "ショートケーキ"], "ショートケーキ（1切れ）", 340, 4.5, 20.0, 36.0, "間食"),
    (["チーズケーキ"], "チーズケーキ（1切れ）", 310, 5.5, 20.0, 26.0, "間食"),
    (["シュークリーム"], "シュークリーム（1個）", 230, 4.5, 14.0, 21.0, "間食"),
    (["プリン"], "カスタードプリン（1個）", 170, 5.0, 7.0, 21.0, "間食"),
    (["アイスクリーム", "アイス", "バニラアイス"], "アイスクリーム（1個）", 210, 3.5, 12.0, 22.0, "間食"),
    (["チョコレート", "チョコ"], "チョコレート（半板・25g）", 140, 2.0, 9.0, 13.0, "間食"),
    (["ポテトチップス", "ポテチ"], "ポテトチップス（1袋60g）", 335, 3.0, 21.0, 33.0, "間食"),
    (["ナッツ", "アーモンド", "ミックスナッツ"], "素焼きミックスナッツ（30g）", 190, 5.5, 16.5, 5.0, "間食"),
    (["どら焼き", "和菓子", "大福"], "和菓子（1個）", 220, 4.5, 1.5, 48.0, "間食"),

    # 飲み物
    (["ブラックコーヒー", "コーヒー", "アイスコーヒー"], "ブラックコーヒー", 5, 0.3, 0.0, 1.0, "飲み物"),
    (["カフェラテ", "カフェオレ"], "カフェラテ（M・無糖）", 120, 5.5, 6.0, 10.0, "飲み物"),
    (["抹茶ラテ"], "抹茶ラテ（M）", 210, 5.5, 6.5, 32.0, "飲み物"),
    (["緑茶", "お茶", "麦茶", "烏龍茶", "水"], "お茶・水", 0, 0.0, 0.0, 0.0, "飲み物"),
    (["牛乳", "ミルク"], "牛乳（200ml）", 134, 6.6, 7.6, 9.6, "飲み物"),
    (["豆乳"], "無調整豆乳（200ml）", 92, 7.2, 4.0, 6.2, "飲み物"),
    (["オレンジジュース", "ジュース", "コーラ", "炭酸飲料"], "ジュース・清涼飲料（350ml）", 150, 0.0, 0.0, 37.0, "飲み物"),
    (["ビール", "生ビール"], "ビール（中ジョッキ・500ml）", 200, 1.5, 0.0, 15.5, "お酒"),
    (["ハイボール"], "ハイボール（1杯）", 70, 0.0, 0.0, 0.0, "お酒"),
    (["チューハイ", "レモンサワー"], "チューハイ・サワー（350ml）", 160, 0.0, 0.0, 14.0, "お酒"),
    (["ワイン"], "ワイン（グラス1杯）", 90, 0.2, 0.0, 2.0, "お酒"),
    (["日本酒"], "日本酒（1合）", 185, 0.7, 0.0, 6.5, "お酒"),
]

# Portion modifiers
PORTION_MULTIPLIERS: List[Tuple[List[str], float, str]] = [
    (["大盛り", "大盛", "特盛", "ダブル", "2人前", "メガ"], 1.4, "大盛り"),
    (["少なめ", "小盛り", "小盛", "ミニ", "半分", "ハーフ"], 0.7, "少なめ"),
]

# Category fallback keywords when exact meal isn't in dictionary
CATEGORY_FALLBACKS: List[Tuple[List[str], str, int, float, float, float]] = [
    (["定食", "御膳", "セット"], "定食系メニュー（概算）", 750, 27.0, 24.0, 98.0),
    (["丼", "重", "ライス"], "丼・ご飯系メニュー（概算）", 660, 20.0, 18.0, 96.0),
    (["麺", "ラーメン", "パスタ", "うどん", "そば"], "麺類メニュー（概算）", 520, 16.0, 14.0, 78.0),
    (["揚げ", "フライ", "カツ", "天ぷら", "唐揚"], "揚げ物系メニュー（概算）", 450, 18.0, 28.0, 28.0),
    (["炒め", "焼き", "ソテー", "グリル"], "炒め・焼き物メニュー（概算）", 340, 18.0, 20.0, 18.0),
    (["煮", "蒸し", "鍋"], "煮物・鍋系メニュー（概算）", 240, 15.0, 8.0, 24.0),
    (["サラダ", "野菜", "マリネ", "おひたし"], "サラダ・野菜系（概算）", 110, 3.0, 5.0, 12.0),
    (["スープ", "汁", "ポタージュ"], "汁物・スープ（概算）", 110, 4.0, 4.0, 12.0),
    (["パン", "サンド", "バーガー", "トースト"], "パン・軽食系（概算）", 320, 10.0, 12.0, 42.0),
    (["ケーキ", "スイーツ", "菓子", "プリン", "パフェ"], "スイーツ・間食（概算）", 260, 4.5, 13.0, 31.0),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def estimate_from_text(query: str, portion: str = "normal") -> Dict[str, Any]:
    """Estimate calories and PFC from a Japanese/general meal name at zero cost."""
    raw = query.strip()
    norm = _normalize(raw)
    if not norm:
        return {
            "matched_name": "食事（未入力）",
            "calories": 500,
            "protein": 18.0,
            "fat": 16.0,
            "carbs": 65.0,
            "confidence": "low",
            "method": "default",
            "note": "メニュー名が空のため標準的な1食分で概算しました。",
            "candidates": [],
        }

    # Check text-embedded portion modifiers unless explicitly passed
    multiplier = {"small": 0.7, "normal": 1.0, "large": 1.4}.get(portion, 1.0)
    portion_note = ""
    if portion == "normal":
        for kws, mult, label in PORTION_MULTIPLIERS:
            if any(k in norm for k in kws):
                multiplier = mult
                portion_note = f"（{label}補正 ×{mult}）"
                break

    # Score dictionary entries
    scored: List[Tuple[int, Tuple[List[str], str, int, float, float, float, str]]] = []
    for entry in FOOD_DICTIONARY:
        kws, cname, kcal, p, f, c, cat = entry
        best_score = 0
        for kw in kws:
            kw_n = _normalize(kw)
            if norm == kw_n:
                best_score = max(best_score, 100 + len(kw_n))
            elif kw_n in norm:
                best_score = max(best_score, 60 + len(kw_n))
            elif norm in kw_n and len(norm) >= 2:
                best_score = max(best_score, 40 + len(norm))
        if best_score > 0:
            scored.append((best_score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    if scored:
        _, top = scored[0]
        _, cname, kcal, p, f, c, cat = top
        candidates = [
            {
                "name": e[1],
                "calories": round(e[2] * multiplier),
                "protein": round(e[3] * multiplier, 1),
                "fat": round(e[4] * multiplier, 1),
                "carbs": round(e[5] * multiplier, 1),
                "category": e[6],
            }
            for _, e in scored[:5]
        ]
        return {
            "matched_name": raw if len(raw) > len(cname) else cname,
            "calories": round(kcal * multiplier),
            "protein": round(p * multiplier, 1),
            "fat": round(f * multiplier, 1),
            "carbs": round(c * multiplier, 1),
            "confidence": "medium" if scored[0][0] >= 60 else "low",
            "method": "dictionary",
            "note": f"内蔵辞書「{cname}」から概算{portion_note}",
            "candidates": candidates,
        }

    # Fallback by cooking style / category keywords
    for kws, label, kcal, p, f, c in CATEGORY_FALLBACKS:
        if any(_normalize(k) in norm for k in kws):
            return {
                "matched_name": raw,
                "calories": round(kcal * multiplier),
                "protein": round(p * multiplier, 1),
                "fat": round(f * multiplier, 1),
                "carbs": round(c * multiplier, 1),
                "confidence": "low",
                "method": "keyword_fallback",
                "note": f"キーワード推定（{label}）で概算{portion_note}。必要に応じて数値を微調整してください。",
                "candidates": [],
            }

    # Final generic fallback
    return {
        "matched_name": raw,
        "calories": round(520 * multiplier),
        "protein": round(18.0 * multiplier, 1),
        "fat": round(17.0 * multiplier, 1),
        "carbs": round(68.0 * multiplier, 1),
        "confidence": "low",
        "method": "generic_fallback",
        "note": f"辞書に完全一致がないため一般的な1食分として概算{portion_note}。必要に応じて調整してください。",
        "candidates": [],
    }


def estimate_from_image_heuristic(
    filename: str = "",
    hint_text: str = "",
    color_profile: Optional[Dict[str, float]] = None,
    portion: str = "normal",
) -> Dict[str, Any]:
    """
    Zero-cost image estimation using:
    1) User hint text or filename if informative
    2) Client-extracted RGB color/brightness profile (green ratio, warm/brown ratio, bright/white ratio)
    Returns a primary estimate + quick-pick candidate meals for one-tap correction.
    """
    # If hint text or meaningful filename is available, try text estimation first
    clean_filename = re.sub(r"\.[a-zA-Z0-9]+$", "", filename or "")
    clean_filename = re.sub(r"^(img|dsc|photo|pxl|screenshot|image)[-_0-9]*", "", clean_filename, flags=re.IGNORECASE).strip()

    combined_hint = hint_text.strip() or clean_filename
    if combined_hint:
        res = estimate_from_text(combined_hint, portion=portion)
        if res["method"] in ("dictionary", "keyword_fallback"):
            res["method"] = "photo_hint"
            res["note"] = f"写真＋ヒント「{combined_hint}」から概算（無料モード）。"
            return res

    # Color-based heuristic (0 cost, runs without any API)
    cp = color_profile or {}
    green = float(cp.get("green_ratio", 0.2))
    warm = float(cp.get("warm_ratio", 0.35))
    bright = float(cp.get("brightness", 0.55))

    multiplier = {"small": 0.7, "normal": 1.0, "large": 1.4}.get(portion, 1.0)

    if green >= 0.32:
        profile_label = "緑色・野菜系プレート"
        base = ("野菜中心のヘルシープレート / サラダボウル", 320, 16.0, 11.0, 36.0)
        suggestions = ["野菜サラダ（ドレッシング付）", "焼き魚定食", "サラダチキン", "豚の生姜焼き定食"]
    elif warm >= 0.45 and bright < 0.6:
        profile_label = "こんがり系（揚げ物・肉・丼・カレー）"
        base = ("肉・揚げ物・丼系メニュー（概算）", 740, 24.0, 28.0, 92.0)
        suggestions = ["唐揚げ定食", "牛丼（並盛）", "カレーライス", "とんかつ定食", "ハンバーグ定食"]
    elif bright >= 0.68:
        profile_label = "白・明るめ（麺類・パン・軽食）"
        base = ("麺類・パン・軽食メニュー（概算）", 480, 14.0, 13.0, 74.0)
        suggestions = ["醤油ラーメン", "うどん（1杯）", "ミックスサンドイッチ", "おにぎり（1個）", "バタートースト"]
    else:
        profile_label = "バランス系定食・プレート"
        base = ("一般的な1食（定食・プレート概算）", 620, 22.0, 20.0, 82.0)
        suggestions = ["焼き魚定食", "幕の内弁当", "親子丼", "ミートソーススパゲティ", "醤油ラーメン"]

    candidates = []
    for s in suggestions:
        est = estimate_from_text(s, portion=portion)
        candidates.append({
            "name": s,
            "calories": est["calories"],
            "protein": est["protein"],
            "fat": est["fat"],
            "carbs": est["carbs"],
        })

    return {
        "matched_name": base[0],
        "calories": round(base[1] * multiplier),
        "protein": round(base[2] * multiplier, 1),
        "fat": round(base[3] * multiplier, 1),
        "carbs": round(base[4] * multiplier, 1),
        "confidence": "low",
        "method": "photo_color_heuristic",
        "note": f"写真の色味（{profile_label}）から0円ローカル概算。下の候補から近い料理を選ぶと精度が上がります。",
        "candidates": candidates,
    }


def estimate_with_gemini(
    api_key: str,
    query: str = "",
    image_data_url: str = "",
    portion: str = "normal",
) -> Optional[Dict[str, Any]]:
    """
    Optional ultra-low-cost AI estimation using Gemini 2.5 Flash-Lite.
    Only called if the user explicitly configures an API key and enables AI mode.
    """
    if not api_key:
        return None

    portion_jp = {"small": "少なめ", "normal": "普通盛り", "large": "大盛り"}.get(portion, "普通盛り")
    prompt_text = (
        "あなたは栄養管理アシスタントです。提供された食事の名前または写真から、"
        f"料理名と概算の栄養価（量: {portion_jp}）をJSONのみで返してください。"
        "キーは必ず matched_name (文字列), calories (整数kcal), protein (小数g), fat (小数g), carbs (小数g), note (短い日本語説明) にしてください。"
    )
    if query:
        prompt_text += f"\n補足・メニュー名: {query}"

    parts: List[Dict[str, Any]] = [{"text": prompt_text}]
    if image_data_url and "," in image_data_url:
        header, b64 = image_data_url.split(",", 1)
        mime = "image/jpeg"
        if "image/png" in header:
            mime = "image/png"
        elif "image/webp" in header:
            mime = "image/webp"
        parts.append({"inline_data": {"mime_type": mime, "data": b64}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-lite:generateContent?key={api_key.strip()}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return {
            "matched_name": str(parsed.get("matched_name") or query or "AI識別メニュー"),
            "calories": int(round(float(parsed.get("calories", 500)))),
            "protein": round(float(parsed.get("protein", 18.0)), 1),
            "fat": round(float(parsed.get("fat", 16.0)), 1),
            "carbs": round(float(parsed.get("carbs", 65.0)), 1),
            "confidence": "high",
            "method": "gemini_flash_lite",
            "note": str(parsed.get("note") or "Gemini Flash-Liteによる低コストAI概算"),
            "candidates": [],
        }
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return None
