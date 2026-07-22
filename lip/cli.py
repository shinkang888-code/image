"""LIP CLI — python -m lip {doctor,list,run,render,nodes,dashboard}."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .comfy_client import ComfyClient, MockComfyClient
from .config import load_config
from .factory import Factory
from .jobs import JobStore
from .manifest import Manifest
from .nodes import NodeRegistry, ensure_default_node
from .optimize import optimize
from .prompts import load_prompts
from .scene import NEGATIVE, load_scene, scene_to_prompt
from .workflow import build_img2img_workflow


def _registry(cfg) -> NodeRegistry:
    reg = NodeRegistry(cfg.nodes_file)
    ensure_default_node(reg, cfg.comfy_host)
    return reg


def _online_engines(cfg, reg: NodeRegistry) -> list[tuple[str, object]]:
    """활성 노드를 헬스체크해 온라인 노드의 (이름, 클라이언트) 목록 반환."""
    engines: list[tuple[str, object]] = []
    for n in reg.active_nodes():
        c = ComfyClient(base_url=n.base_url)
        if c.ping():
            reg.update_status(n.id, "online")
            engines.append((n.name, c))
        else:
            reg.update_status(n.id, "offline", "ping 실패")
    return engines


def _doctor_models(cfg, client: ComfyClient) -> list[str]:
    """엔진별 필수 모델 존재 여부 점검. 문제 메시지 목록 반환."""
    issues: list[str] = []
    p = cfg.profile
    if p.engine == "gguf":
        checks = [
            ("unet", p.unet),
            ("text_encoders", p.clip),
            ("vae", p.vae),
        ]
    else:
        checks = [("checkpoints", p.checkpoint)]
    for folder, name in checks:
        names = client.list_models(folder)
        if names is None:
            issues.append(f"모델 목록 조회 실패(/models/{folder}) — ComfyUI 버전 확인")
            continue
        # basename 또는 상대경로로 매칭
        basenames = {Path(x).name for x in names}
        if name not in basenames and name not in names:
            issues.append(f"누락: models/{folder}/{name}")
        else:
            print(f"  ✓ models/{folder}/{name}")
    return issues


def cmd_doctor(args) -> int:
    cfg = load_config(args.config)
    reg = _registry(cfg)
    p = cfg.profile
    if p.engine == "gguf":
        print(f"engine  : gguf  unet={p.unet}  {p.width}x{p.height} "
              f"{p.steps}steps cfg{p.cfg} sampler={p.sampler}")
    else:
        print(f"engine  : sdxl  ckpt={p.checkpoint}  {p.width}x{p.height} "
              f"{p.steps}steps cfg{p.cfg} quality={cfg.quality}")
    print(f"output  : FHD{cfg.output.target} formats={cfg.formats} workers={cfg.workers} "
          f"takes={cfg.takes} retries={cfg.retries}")
    print("nodes   :")
    any_online = False
    model_issues: list[str] = []
    for n in reg.list():
        c = ComfyClient(base_url=n.base_url)
        ok = c.ping()
        any_online = any_online or ok
        reg.update_status(n.id, "online" if ok else "offline")
        print(f"  {'●' if ok else '○'} {n.name:<14} {n.base_url}  [{'online' if ok else 'offline'}]"
              f"{' (active)' if n.active else ''}")
        if ok and n.active:
            print("models  :")
            model_issues.extend(_doctor_models(cfg, c))
    if not any_online:
        print("→ 온라인 노드 없음. `scripts/start-comfy.ps1` 로 ComfyUI 기동 후 재시도.")
        print("→ 또는 `python -m lip run --dry-run` 으로 파이프라인 검증.")
        return 1
    if model_issues:
        for m in model_issues:
            print(f"→ {m}")
        return 2
    print("→ 공장 준비 완료. `python -m lip run --count 3` 또는 `scripts/factory.ps1`")
    return 0


def cmd_list(args) -> int:
    prompts = load_prompts(args.config and load_config(args.config).catalog, args.tag)
    print(f"{len(prompts)} prompts" + (f" (tag={args.tag})" if args.tag else ""))
    for p in prompts[: args.limit]:
        print(f"  {p.tag}/{p.id}  {p.positive[:90]}")
    if len(prompts) > args.limit:
        print(f"  ... (+{len(prompts) - args.limit} more)")
    return 0


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    if args.quality:
        cfg.quality = True
    if args.takes:
        cfg.takes = args.takes
    prompts = load_prompts(cfg.catalog, args.tag)
    if not prompts:
        print("no prompts", file=sys.stderr)
        return 1
    reg = _registry(cfg)
    store = JobStore()

    if args.dry_run:
        engines = [("mock", MockComfyClient((cfg.profile.width, cfg.profile.height)))]
    else:
        engines = _online_engines(cfg, reg)
        if not engines:
            print("온라인 Compute Node 없음. `python -m lip nodes add` 로 등록하거나 --dry-run.",
                  file=sys.stderr)
            return 1

    if args.dashboard:
        from .dashboard import serve_dashboard
        serve_dashboard(store, reg, cfg.out_dir, cfg.dashboard_port, block=False)
        print(f"대시보드: http://localhost:{cfg.dashboard_port}")

    manifest = Manifest(cfg.out_dir / "manifest.jsonl")
    factory = Factory(cfg, engine=engines[0][1], manifest=manifest, store=store, engines=engines)
    mode = "DRY-RUN(mock)" if args.dry_run else f"LIVE({len(engines)} nodes)"
    print(f"LIP {mode} — {len(prompts)} prompts, target={args.count or 'all'}, "
          f"resume={len(manifest)} done, workers={cfg.workers}, quality={cfg.quality}, takes={cfg.takes}")
    n = factory.run(prompts, args.count)
    print(f"완료: {n}장 생성 → {cfg.out_dir}/")

    if args.dashboard:
        print("대시보드 유지 중 — Ctrl+C 로 종료.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_render(args) -> int:
    """img2img — 조감도 스냅샷/씬을 실사화 (로컬 render.ts 대체)."""
    cfg = load_config(args.config)
    if args.quality:
        cfg.quality = True
    reg = _registry(cfg)

    prompt = args.prompt
    if args.scene:
        prompt = scene_to_prompt(load_scene(args.scene), args.style) if not prompt \
            else prompt
        if not args.prompt:
            print(f"씬 프롬프트: {prompt[:100]}...")
    if not prompt:
        print("--prompt 또는 --scene 필요", file=sys.stderr)
        return 1
    if not args.image:
        print("--image (조감도 스냅샷 PNG) 필요", file=sys.stderr)
        return 1

    if args.dry_run:
        client = MockComfyClient((cfg.profile.width, cfg.profile.height))
    else:
        engines = _online_engines(cfg, reg)
        if not engines:
            print("온라인 노드 없음. --dry-run 또는 nodes add.", file=sys.stderr)
            return 1
        client = engines[0][1]

    image_name = client.upload_image(args.image)
    seed = cfg.base_seed
    wf = build_img2img_workflow(image_name, prompt, NEGATIVE, seed, cfg.profile,
                                denoise=args.denoise, quality=cfg.quality)
    raw = client.generate(wf)
    encoded = optimize(raw, cfg.output, cfg.formats)
    out = Path(args.out or (cfg.out_dir / "render"))
    out.mkdir(parents=True, exist_ok=True)
    for e in encoded:
        (out / f"render.{e.fmt}").write_bytes(e.data)
    sizes = ", ".join(f"{e.fmt} {e.bytes_len // 1024}KB" for e in encoded)
    print(f"실사화 완료 → {out}/ ({sizes})")
    return 0


def cmd_nodes(args) -> int:
    cfg = load_config(args.config)
    reg = NodeRegistry(cfg.nodes_file)  # 기본노드 자동생성 없이 그대로 조회/편집
    if args.node_cmd == "add":
        n = reg.upsert(name=args.name, base_url=args.url)
        print(f"등록: {n.name} → {n.base_url} (id={n.id})")
    elif args.node_cmd == "rm":
        print("삭제됨" if reg.remove(args.id) else "id 없음")
    else:  # list
        nodes = reg.list()
        print(f"{len(nodes)} nodes")
        for n in nodes:
            print(f"  {'●' if n.active else '○'} {n.id}  {n.name:<14} {n.base_url}  [{n.status}]")
    return 0


def cmd_dashboard(args) -> int:
    """읽기 전용 대시보드 (기존 out/ 매니페스트·노드 조회용)."""
    cfg = load_config(args.config)
    from .dashboard import serve_dashboard
    reg = _registry(cfg)
    store = JobStore()
    store.event("info", "읽기 전용 대시보드 — run --dashboard 로 라이브 관제")
    print(f"대시보드: http://localhost:{cfg.dashboard_port}  (Ctrl+C 종료)")
    try:
        serve_dashboard(store, reg, cfg.out_dir, cfg.dashboard_port, block=True)
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows cp949 콘솔에서도 상태 문자(—, →, ●)가 깨지지 않게
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(prog="lip", description="Lexi Image Factory")
    ap.add_argument("--config", help="lip.toml 경로")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="노드 연결·설정 점검")
    d.set_defaults(func=cmd_doctor)

    l = sub.add_parser("list", help="전개된 프롬프트 미리보기")
    l.add_argument("--tag", action="append")
    l.add_argument("--limit", type=int, default=20)
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("run", help="연속 생성")
    r.add_argument("--count", type=int, default=None)
    r.add_argument("--tag", action="append")
    r.add_argument("--dry-run", action="store_true", help="GPU 없이 Mock 엔진")
    r.add_argument("--dashboard", action="store_true", help="작업제어 대시보드 동시 실행")
    r.add_argument("--quality", action="store_true", help="ESRGAN 고화질 모드")
    r.add_argument("--takes", type=int, default=None, help="프롬프트당 시드 변주 장수")
    r.set_defaults(func=cmd_run)

    rn = sub.add_parser("render", help="img2img 실사화 (조감도/씬 → 실사, 로컬 render.ts 대체)")
    rn.add_argument("--image", help="참조 스냅샷 PNG 경로")
    rn.add_argument("--scene", help="Lexi Draft Scene JSON → 프롬프트 자동합성")
    rn.add_argument("--prompt", help="직접 프롬프트 (씬보다 우선)")
    rn.add_argument("--style", default="modern minimalist")
    rn.add_argument("--denoise", type=float, default=0.6)
    rn.add_argument("--quality", action="store_true")
    rn.add_argument("--out", help="출력 디렉토리")
    rn.add_argument("--dry-run", action="store_true")
    rn.set_defaults(func=cmd_render)

    nd = sub.add_parser("nodes", help="Compute Node 등록/조회 (멀티 GPU 분산)")
    nsub = nd.add_subparsers(dest="node_cmd")
    na = nsub.add_parser("add"); na.add_argument("--name", required=True); na.add_argument("--url", required=True)
    nsub.add_parser("list")
    nr = nsub.add_parser("rm"); nr.add_argument("--id", required=True)
    nd.set_defaults(func=cmd_nodes, node_cmd="list")

    db = sub.add_parser("dashboard", help="읽기 전용 대시보드 서버")
    db.set_defaults(func=cmd_dashboard)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
