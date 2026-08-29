"""app_emojis.py — logo app hiện ngay trong tin doanh thu, dưới dạng emoji server.

🔴 Sếp 2026-08-29: "Hiện đúng tên và cả logo app ra".

Discord KHÔNG cho gắn ảnh vào từng dòng của một embed field — chỉ có đúng một
`thumbnail` cho cả embed. Muốn mỗi app một logo thì chỉ còn hai đường:

  1. Mỗi app một embed riêng → tối đa 10 embed/tin, mà fleet đang 8 partner ×
     5 app ⇒ phải xé thành nhiều tin, đọc còn mệt hơn hiện tại.
  2. Upload logo thành **emoji của server** rồi chèn `<:slug:id>` vào text.

Chọn (2). Đánh đổi phải biết trước: emoji KHÔNG render bên trong khối ```ansi```
nên bảng số mất phần căn cột + màu ANSI, đổi lấy logo và tên đọc được.

Giới hạn thật của server (đo lúc viết: boost tier 0 → 50 slot, đang dùng 0):
báo cáo hiện tối đa 8 partner × 5 app = 40 logo, vừa đủ. Vẫn phải có đường dọn
cho ngày fleet phình hoặc server đổi tier — xem `_ensure_slot`.

Nguồn ảnh: `public/data/app_icons.json` (do gen_app_icons.py sinh từ snapshot
apps-status). Ảnh webp/không-đuôi được convert sang PNG 128px vì Discord chỉ
nhận PNG/JPEG/GIF và trần 256KB.
"""
import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

DISCORD_API = "https://discord.com/api/v10"
HTTP_TIMEOUT = 25
EMOJI_PX = 128                     # Discord hiển thị ~32px, 128 là thừa nét
STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "public", "data", "app_emojis.json")
ICONS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "public", "data", "app_icons.json")


SNAPSHOT_URL = ("https://raw.githubusercontent.com/conmangangqua/"
                "apps-status/data/snapshot.json")


def _icons_by_property() -> Dict[str, str]:
    """{property_id: url icon} lấy thẳng snapshot apps-status.

    Cố ý KHÔNG tra `app_icons.json` theo tên: file đó khoá theo tên hiển thị, mà
    tên chính là thứ vừa sai (app rebrand, property đặt theo project cũ) — tra
    theo tên thì app mới không bao giờ có logo. `property_id` là khoá duy nhất
    không đổi khi app đổi tên.
    """
    tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(SNAPSHOT_URL)
    if tok:
        req.add_header("Authorization", f"token {tok}")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            snap = json.load(r)
    except Exception as e:
        print(f"   ⚠️  không đọc được snapshot để lấy logo ({str(e)[:50]})")
        return {}
    out = {}
    for part in snap.get("partners", []):
        pslug = part.get("slug") or part.get("name") or ""
        for a in part.get("apps", []):
            icon = (a.get("store_info") or {}).get("icon_url") or ""
            if not icon:
                ic = a.get("icon") or ""
                if ic.startswith("http"):
                    icon = ic
                elif ic and pslug:
                    icon = f"https://conmangangqua.github.io/{pslug}_app/{ic.lstrip('/')}"
            pid = (((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}).get("property_id")
            if pid and icon:
                out[str(pid)] = icon
    return out


def _token() -> str:
    return (os.environ.get("DISCORD_BOT_TOKEN")
            or os.environ.get("DISCORD_BOT_TOKEN_TRANQUIL") or "").strip()


def _api(method: str, path: str, body: Optional[dict] = None):
    req = urllib.request.Request(
        f"{DISCORD_API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Authorization", f"Bot {_token()}")
    req.add_header("Content-Type", "application/json")
    # Discord TỪ CHỐI (403) User-Agent mặc định của urllib. Cùng token đó gọi
    # bằng curl thì 200 — nên lỗi rất dễ bị đọc nhầm thành "token hỏng/thiếu
    # quyền". Bắt buộc khai UA đúng dạng bot.
    req.add_header("User-Agent",
                   "DiscordBot (https://tranquilmind.co, 1.0) revenue-bot")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def _guild_id() -> Optional[str]:
    gid = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if gid:
        return gid
    try:
        gs = _api("GET", "/users/@me/guilds")
        return gs[0]["id"] if gs else None
    except Exception as e:
        print(f"   ⚠️  không lấy được guild id ({e})")
        return None


def _slug(name: str) -> str:
    """Tên emoji Discord: chỉ [A-Za-z0-9_], 2–32 ký tự."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_").lower()
    s = re.sub(r"_+", "_", s)[:32]
    if len(s) < 2:
        s = f"app_{s}" if s else "app_x"
    return s


def _fetch_png(url: str) -> Optional[bytes]:
    """Tải icon → PNG vuông EMOJI_PX. None nếu hỏng (KHÔNG ném lỗi lên báo cáo)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "revenue-bot"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read()
    except Exception as e:
        print(f"   ⚠️  tải icon hỏng ({str(e)[:50]}) — bỏ qua logo app này")
        return None
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        im = im.resize((EMOJI_PX, EMOJI_PX), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        out = buf.getvalue()
    except Exception as e:
        print(f"   ⚠️  ảnh không đọc được ({str(e)[:50]})")
        return None
    if len(out) > 256_000:          # trần cứng của Discord
        return None
    return out


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _ensure_slot(gid: str, existing: List[dict], st: dict, cap: int) -> bool:
    """Còn chỗ trống thì thôi; hết thì xoá emoji LÂU NHẤT KHÔNG DÙNG.

    Không xoá bừa: chỉ đụng emoji do chính job này tạo (có trong state), tuyệt
    đối không động vào emoji người ta tự thêm vào server.
    """
    if len(existing) < cap:
        return True
    mine = {v["id"]: k for k, v in st.items() if isinstance(v, dict) and v.get("id")}
    victims = sorted(
        [e for e in existing if e["id"] in mine],
        key=lambda e: st[mine[e["id"]]].get("last_used", 0))
    if not victims:
        print("   ⚠️  hết slot emoji mà không có cái nào của job này để dọn")
        return False
    v = victims[0]
    try:
        _api("DELETE", f"/guilds/{gid}/emojis/{v['id']}")
        st.pop(mine[v["id"]], None)
        existing.remove(v)
        return True
    except Exception as e:
        print(f"   ⚠️  xoá emoji cũ hỏng ({str(e)[:50]})")
        return False


def ensure_emojis(apps: List[dict], cap: int = 50) -> Dict[str, str]:
    """{tên app: '<:slug:id>'} cho các app sắp hiện trong báo cáo.

    App nào không có icon / tải hỏng / hết slot thì đơn giản là KHÔNG có mặt
    trong map — chỗ gọi tự bỏ qua logo, báo cáo vẫn gửi bình thường. Logo là
    phần trang trí, không được phép làm chết tin doanh thu.
    """
    if not _token():
        print("   ⚠️  thiếu DISCORD_BOT_TOKEN — bỏ qua logo app")
        return {}
    gid = _guild_id()
    if not gid:
        return {}
    icons_by_pid = _icons_by_property()
    try:
        icons_by_name = json.load(open(ICONS_FILE, encoding="utf-8"))
    except Exception:
        icons_by_name = {}
    if not icons_by_pid and not icons_by_name:
        print("   ⚠️  không có nguồn icon nào — bỏ qua logo app")
        return {}
    try:
        existing = _api("GET", f"/guilds/{gid}/emojis") or []
    except Exception as e:
        print(f"   ⚠️  không đọc được emoji server ({str(e)[:60]})")
        return {}

    st = _load_state()
    by_slug = {e["name"]: e for e in existing}
    out, now = {}, int(time.time())

    for a in apps:
        nm = a.get("app_name") or ""
        pid = str(a.get("property_id") or "")
        if not nm:
            continue
        slug = _slug(nm)
        hit = by_slug.get(slug)
        if hit:
            out[nm] = f"<:{slug}:{hit['id']}>"
            st[nm] = {"id": hit["id"], "slug": slug, "last_used": now}
            continue
        url = icons_by_pid.get(pid) or icons_by_name.get(nm) or icons_by_name.get(nm.lower())
        if not url:
            continue
        png = _fetch_png(url)
        if not png:
            continue
        if not _ensure_slot(gid, existing, st, cap):
            break
        try:
            data = "data:image/png;base64," + base64.b64encode(png).decode()
            new = _api("POST", f"/guilds/{gid}/emojis",
                       {"name": slug, "image": data})
        except urllib.error.HTTPError as e:
            # 429 = rate limit; 400 = tên/ảnh không hợp lệ. Cả hai đều chỉ mất
            # logo của MỘT app, không được làm hỏng cả báo cáo.
            print(f"   ⚠️  tạo emoji '{slug}' hỏng: HTTP {e.code}")
            continue
        except Exception as e:
            print(f"   ⚠️  tạo emoji '{slug}' hỏng: {str(e)[:50]}")
            continue
        if not new:
            continue
        existing.append(new)
        by_slug[slug] = new
        out[nm] = f"<:{slug}:{new['id']}>"
        st[nm] = {"id": new["id"], "slug": slug, "last_used": now}
        time.sleep(0.4)             # nới tay với rate limit khi tạo hàng loạt

    _save_state(st)
    print(f"   🖼️  logo app sẵn sàng: {len(out)}/{len(apps)}")
    return out
