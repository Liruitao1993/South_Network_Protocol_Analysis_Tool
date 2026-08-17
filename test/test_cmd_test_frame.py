# -*- coding: utf-8 -*-
"""测试 0xF0 测试帧（2.0测试 / Bitloading表下发）解析"""

import _path_setup  # noqa: E402

from csg_new_gen_cmd_payloads import parse_command_payload


def main():
    # 来自 GUI 截图的 Bitloading表下发 测试帧（业务数据单元）
    payload = bytes.fromhex(
        "04 00 28 00 01 06 02 00 01 00 02 00 01 03 EA 01 "
        "18 00 48 04 B6 6D DB 24 49 92 24 49 49 92 24 49 "
        "4A 92 24 49 92 00 00 00 00 00 00 00"
    )
    print(f"payload length: {len(payload)}")
    print(f"payload: {payload.hex(' ')}")
    print()

    table = parse_command_payload(payload, service_id=0xF0, direction=0, msg_port=0, base_offset=0)
    print(f"{'字段':<24} {'原始值':<24} {'解析值':<12} {'说明'}")
    print("-" * 100)
    for name, raw, parsed, desc, start, end in table:
        rng = f"[{start},{end}]" if start is not None and end is not None else ""
        print(f"{name:<24} {raw:<24} {parsed:<12} {desc} {rng}")


if __name__ == "__main__":
    main()

