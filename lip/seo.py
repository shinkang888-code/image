"""검색·권리 메타데이터 — 최소 토큰 XMP 패킷 (명세 §5.1, a364a6e).

파일 내부 XMP 는 **권리·이력용**이다. 검색 노출을 만드는 것은 페이지의
JSON-LD·사이트맵(명세 §5.2 B층)이지 이 패킷이 아니다. 여기서는 저작권 주장,
생산 이력(프롬프트·엔진·시드), AI 생성 고지를 파일에 붙여 재유통돼도
따라가게 한다.

주입 방식: 컨테이너 삽입이 아니라 **인코딩 인자**로 넘긴다.
Pillow 가 WEBP/JPEG/AVIF 모두 save(..., xmp=...) 를 받으므로
추가 I/O·재인코딩이 전부 0 이다(명세의 '인코딩 직후 삽입'보다 한 단계 저렴).
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2"
PRODUCER = "lexi_ai/ipplant"
COPYRIGHT_HOLDER = "steven8kay"
CREATOR = "LEXI AI"
# IPTC 디지털 소스 유형 — AI 생성 고지. 빼면 실사 위장이 되어 플랫폼 리스크.
DIGITAL_SOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"

#: 패킷 상한. 넘으면 프롬프트를 잘라 맞춘다.
#:
#: 명세 초안의 700B 는 달성 불가로 판명됐다 — XMP 는 RDF·네임스페이스 선언이
#: 강제라 **보일러플레이트만으로 850B**(실측)다. 표준 필드(AI 생성 고지·
#: 라이선스·저작권 귀속)를 버리면 줄지만, 그건 이 패킷의 존재 이유다.
#: '최소 토큰' 목표는 가변분에 적용한다 — 실측 가변분 254B.
MAX_PACKET_BYTES = 1200


@dataclass(frozen=True)
class ImageMeta:
    category: str          # "websource"
    subcategory: str       # "storefront"
    prompt: str            # 가변 프롬프트 (품질 접미어 제외)
    recipe: str            # 고정 접미어 사전 키 — "r7"
    engine: str            # "krea2t-q3km"
    seed: int
    caption: str = ""      # 영문 1문장
    license_url: str = ""


def compact_line(m: ImageMeta) -> str:
    """lexi:x — 파이프 구분 1줄. 스펙 §5.1 규약."""
    return (
        f"{SCHEMA_VERSION}|{m.category}/{m.subcategory}|{m.engine}|"
        f"{m.seed}|ipplant|{m.recipe}|{m.prompt}"
    )


def build_xmp(m: ImageMeta, *, max_bytes: int = MAX_PACKET_BYTES) -> bytes:
    """≤max_bytes XMP 패킷. 초과 시 프롬프트만 잘라 맞춘다(구조는 유지)."""
    meta = m
    packet = _render(meta)
    # 프롬프트를 8자씩 줄여가며 상한에 맞춘다. 구조 필드는 절대 버리지 않는다.
    while len(packet) > max_bytes and len(meta.prompt) > 24:
        meta = ImageMeta(**{**meta.__dict__, "prompt": meta.prompt[:-8].rstrip(" ,") + "…"})
        packet = _render(meta)
    return packet


def _render(m: ImageMeta) -> bytes:
    x = _esc(compact_line(m))
    cap = _esc(m.caption)
    lic = _esc(m.license_url)
    body = (
        f'<rdf:Description rdf:about=""'
        f' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        f' xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"'
        f' xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"'
        f' xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"'
        f' xmlns:lexi="https://lexi.ai/ns/iplant/1.0/"'
        f' photoshop:Credit="{PRODUCER}"'
        f' xmpRights:WebStatement="{lic}"'
        f' Iptc4xmpExt:DigitalSourceType="{DIGITAL_SOURCE}"'
        f' lexi:x="{x}">'
        f"<dc:creator><rdf:Seq><rdf:li>{CREATOR}</rdf:li></rdf:Seq></dc:creator>"
        f"<dc:rights><rdf:Alt><rdf:li xml:lang=\"x-default\">© {COPYRIGHT_HOLDER}</rdf:li>"
        f"</rdf:Alt></dc:rights>"
        + (f"<dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">{cap}</rdf:li>"
           f"</rdf:Alt></dc:description>" if cap else "")
        + "</rdf:Description>"
    )
    return (
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        f"{body}"
        "</rdf:RDF></x:xmpmeta><?xpacket end=\"w\"?>"
    ).encode("utf-8")


def read_compact(data: bytes) -> str | None:
    """파일 바이트에서 lexi:x 값을 되읽는다(탐색기 표시·검증용)."""
    key = b'lexi:x="'
    i = data.find(key)
    if i < 0:
        return None
    j = data.find(b'"', i + len(key))
    if j < 0:
        return None
    return _unesc(data[i + len(key):j].decode("utf-8", "replace"))


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _unesc(s: str) -> str:
    return (s.replace("&quot;", '"').replace("&gt;", ">")
             .replace("&lt;", "<").replace("&amp;", "&"))
