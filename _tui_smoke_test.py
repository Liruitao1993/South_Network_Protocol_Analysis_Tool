"""Quick smoke test for TUI app"""
import sys
sys.path.insert(0, r'E:\python\南网解析工具')

from tui_app import ProtocolParserTUI, clean_hex_input, extract_frames_for_protocol

# Test 1: clean_hex_input
print("1. clean_hex_input:", clean_hex_input("68 11 01 01 01 68 11 02") == "6811010101681102")

# Test 2: Frame extraction for South Grid (valid frame: L=8)
sg_frame = "68 08 00 00 00 00 00 16"
clean = clean_hex_input(sg_frame)
frames = extract_frames_for_protocol(clean, 0)
print(f"2. SG frames extracted: {len(frames)}, frame={frames}")

if frames:
    fbytes = bytes.fromhex(frames[0])
    app = ProtocolParserTUI()
    parser = app._get_current_parser()
    data = parser.parse_to_table(fbytes)
    print(f"3. SG parse result rows: {len(data)}")
    for r in data[:8]:
        print(f"   {str(r[0]):30s} | {str(r[2]):20s} | {str(r[3])[:50]}")

    # Test 4: Validator
    print("\n4. Testing validator...")
    from validator.nw_validator import NWValidator
    v = NWValidator()
    result = v.verify(fbytes)
    print(f"   Valid: {result.valid}, Pass: {result.pass_count}, Fail: {result.fail_count}")
    for c in result.checks:
        print(f"   {c.icon} {c.name}: expected={c.expected} actual={c.actual} msg={c.message[:60]}")

# Test 5: Batch parsing
print("\n5. Testing batch extraction...")
batch_text = "68 08 00 00 00 00 00 16\n68 08 00 00 00 00 00 16"
clean_batch = clean_hex_input(batch_text, keep_newlines=True)
batch_frames = extract_frames_for_protocol(clean_batch, 0)
print(f"   Batch frames extracted: {len(batch_frames)}")

# Test 6: CSG frame extraction
print("\n6. CSG frame extraction...")
csg_text = "A0000000000000000000000000000000B000000000000000"
csg_frames = extract_frames_for_protocol(csg_text, 8)
print(f"   CSG frames: {len(csg_frames)}")

print("\n=== Smoke test complete ===")
