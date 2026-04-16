"""
生成完整的 DLT645-2007 DI 映射表
"""
import json

def generate_di_map():
    di_map = {}

    # 电能量数据类 (00)
    # 正向有功电能
    for i in range(16):  # 费率 0-15
        di_key = f"0001{i:02X}00"
        if i == 0:
            name = "当前正向有功总电能"
        else:
            name = f"当前正向有功费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}

    # 反向有功电能
    for i in range(16):
        di_key = f"0002{i:02X}00"
        if i == 0:
            name = "当前反向有功总电能"
        else:
            name = f"当前反向有功费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}

    # 组合有功电能
    for i in range(16):
        di_key = f"0003{i:02X}00"
        if i == 0:
            name = "当前组合有功总电能"
        else:
            name = f"当前组合有功费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}

    # 正向无功电能
    for i in range(16):
        di_key = f"0004{i:02X}00"
        if i == 0:
            name = "当前正向无功总电能"
        else:
            name = f"当前正向无功费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 反向无功电能
    for i in range(16):
        di_key = f"0005{i:02X}00"
        if i == 0:
            name = "当前反向无功总电能"
        else:
            name = f"当前反向无功费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 组合无功1电能
    for i in range(16):
        di_key = f"0006{i:02X}00"
        if i == 0:
            name = "当前组合无功1总电能"
        else:
            name = f"当前组合无功1费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 组合无功2电能
    for i in range(16):
        di_key = f"0007{i:02X}00"
        if i == 0:
            name = "当前组合无功2总电能"
        else:
            name = f"当前组合无功2费率{i}电能"
        di_map[di_key] = {"name": name, "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 象限无功电能
    for quadrant in range(1, 5):  # 象限 1-4
        for i in range(16):
            di_key = f"00{quadrant+8}{i:02X}00"  # 0x0A-0x0D
            if i == 0:
                name = f"当前第{quadrant}象限无功总电能"
            else:
                name = f"当前第{quadrant}象限无功费率{i}电能"
            di_map[di_key] = {"name": name, "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 最大需量数据类 (01)
    # 正向有功最大需量
    for i in range(16):
        di_key = f"0101{i:02X}00"
        if i == 0:
            name = "当前正向有功总最大需量及发生时间"
        else:
            name = f"当前正向有功费率{i}最大需量及发生时间"
        di_map[di_key] = {"name": name, "unit": "kW,MM.DDhhmm", "data_type": "XX.XXXX,MDHM", "length": 8}

    # 反向有功最大需量
    for i in range(16):
        di_key = f"0102{i:02X}00"
        if i == 0:
            name = "当前反向有功总最大需量及发生时间"
        else:
            name = f"当前反向有功费率{i}最大需量及发生时间"
        di_map[di_key] = {"name": name, "unit": "kW,MM.DDhhmm", "data_type": "XX.XXXX,MDHM", "length": 8}

    # 变量数据类 (02)
    # 电压
    di_map["02010100"] = {"name": "A相电压", "unit": "V", "data_type": "XXX.X", "length": 2}
    di_map["02010200"] = {"name": "B相电压", "unit": "V", "data_type": "XXX.X", "length": 2}
    di_map["02010300"] = {"name": "C相电压", "unit": "V", "data_type": "XXX.X", "length": 2}

    # 电流
    di_map["02020100"] = {"name": "A相电流", "unit": "A", "data_type": "XXX.XXX", "length": 3}
    di_map["02020200"] = {"name": "B相电流", "unit": "A", "data_type": "XXX.XXX", "length": 3}
    di_map["02020300"] = {"name": "C相电流", "unit": "A", "data_type": "XXX.XXX", "length": 3}

    # 瞬时有功功率
    di_map["03060000"] = {"name": "瞬时总有功功率", "unit": "kW", "data_type": "XX.XXXX", "length": 3}
    di_map["03060100"] = {"name": "瞬时A相有功功率", "unit": "kW", "data_type": "XX.XXXX", "length": 3}
    di_map["03060200"] = {"name": "瞬时B相有功功率", "unit": "kW", "data_type": "XX.XXXX", "length": 3}
    di_map["03060300"] = {"name": "瞬时C相有功功率", "unit": "kW", "data_type": "XX.XXXX", "length": 3}

    # 瞬时无功功率
    di_map["03080000"] = {"name": "瞬时总无功功率", "unit": "kvar", "data_type": "XX.XXXX", "length": 3}
    di_map["03080100"] = {"name": "瞬时A相无功功率", "unit": "kvar", "data_type": "XX.XXXX", "length": 3}
    di_map["03080200"] = {"name": "瞬时B相无功功率", "unit": "kvar", "data_type": "XX.XXXX", "length": 3}
    di_map["03080300"] = {"name": "瞬时C相无功功率", "unit": "kvar", "data_type": "XX.XXXX", "length": 3}

    # 瞬时视在功率
    di_map["030A0000"] = {"name": "瞬时总视在功率", "unit": "kVA", "data_type": "XX.XXXX", "length": 3}
    di_map["030A0100"] = {"name": "瞬时A相视在功率", "unit": "kVA", "data_type": "XX.XXXX", "length": 3}
    di_map["030A0200"] = {"name": "瞬时B相视在功率", "unit": "kVA", "data_type": "XX.XXXX", "length": 3}
    di_map["030A0300"] = {"name": "瞬时C相视在功率", "unit": "kVA", "data_type": "XX.XXXX", "length": 3}

    # 功率因数
    di_map["030B0000"] = {"name": "总功率因数", "unit": "", "data_type": "X.XXX", "length": 2}
    di_map["030B0100"] = {"name": "A相功率因数", "unit": "", "data_type": "X.XXX", "length": 2}
    di_map["030B0200"] = {"name": "B相功率因数", "unit": "", "data_type": "X.XXX", "length": 2}
    di_map["030B0300"] = {"name": "C相功率因数", "unit": "", "data_type": "X.XXX", "length": 2}

    # 相角
    di_map["030C0100"] = {"name": "A相相角", "unit": "°", "data_type": "XXX.X", "length": 2}
    di_map["030C0200"] = {"name": "B相相角", "unit": "°", "data_type": "XXX.X", "length": 2}
    di_map["030C0300"] = {"name": "C相相角", "unit": "°", "data_type": "XXX.X", "length": 2}

    # 谐波数据类 (03)
    # 电压谐波含量
    for i in range(2, 22):  # 2-21次谐波
        di_map[f"0310{i:02X}00"] = {"name": f"A相电压{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}
        di_map[f"0310{i:02X}01"] = {"name": f"B相电压{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}
        di_map[f"0310{i:02X}02"] = {"name": f"C相电压{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}

    # 电流谐波含量
    for i in range(2, 22):
        di_map[f"0311{i:02X}00"] = {"name": f"A相电流{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}
        di_map[f"0311{i:02X}01"] = {"name": f"B相电流{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}
        di_map[f"0311{i:02X}02"] = {"name": f"C相电流{i}次谐波含量", "unit": "%", "data_type": "XXX.X", "length": 2}

    # 电表参数类 (04)
    di_map["04000101"] = {"name": "日期", "unit": "", "data_type": "YYYYMMDD", "length": 4}
    di_map["04000102"] = {"name": "时间", "unit": "", "data_type": "hhmmss", "length": 3}
    di_map["04000103"] = {"name": "最大需量周期", "unit": "min", "data_type": "XX", "length": 1}
    di_map["04000104"] = {"name": "滑差时间", "unit": "min", "data_type": "XX", "length": 1}

    # 通信地址
    di_map["04000401"] = {"name": "通信地址", "unit": "", "data_type": "NNNNNNNNNNNN", "length": 6}

    # 电表运行状态字
    di_map["04000501"] = {"name": "电表运行状态字1", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000502"] = {"name": "电表运行状态字2", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000503"] = {"name": "电表运行状态字3", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000504"] = {"name": "电表运行状态字4", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000505"] = {"name": "电表运行状态字5", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000506"] = {"name": "电表运行状态字6", "unit": "", "data_type": "BS32", "length": 4}
    di_map["04000507"] = {"name": "电表运行状态字7", "unit": "", "data_type": "BS32", "length": 4}

    # 事件记录类 (06)
    di_map["06000001"] = {"name": "事件清零总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}
    di_map["06000002"] = {"name": "编程总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}
    di_map["06000003"] = {"name": "校时总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}

    # 冻结类 (07)
    di_map["07000001"] = {"name": "定时冻结总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}
    di_map["07000002"] = {"name": "瞬时冻结总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}
    di_map["07000003"] = {"name": "日冻结总次数", "unit": "次", "data_type": "XXXXXX", "length": 3}

    # 当前月电能 (上月数据)
    for month in range(1, 13):
        # 上月正向有功
        di_map[f"04{month:02X}0100"] = {"name": f"上{month}月正向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}
        # 上月反向有功
        di_map[f"04{month:02X}0200"] = {"name": f"上{month}月反向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}
        # 上月正向无功
        di_map[f"04{month:02X}0400"] = {"name": f"上{month}月正向无功总电能", "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}
        # 上月反向无功
        di_map[f"04{month:02X}0500"] = {"name": f"上{month}月反向无功总电能", "unit": "kvarh", "data_type": "XXXXXX.XX", "length": 4}

    # 结算日电能 (通过数据类型区分)
    # 结算日1-254
    for settle in range(1, 255):
        # 结算日正向有功
        di_map[f"05{settle:02X}0100"] = {"name": f"结算日{settle}正向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}
        di_map[f"05{settle:02X}0200"] = {"name": f"结算日{settle}反向有功总电能", "unit": "kWh", "data_type": "XXXXXX.XX", "length": 4}

    return di_map


def main():
    di_map = generate_di_map()

    # 统计
    print(f"生成 DI 映射表，共 {len(di_map)} 条记录")

    # 保存到 JSON 文件
    output = {
        "description": "DLT645-2007 电表协议数据标识(DI)映射表",
        "version": "1.1.0",
        "di_map": di_map
    }

    with open('dlt645_di.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"已保存到 dlt645_di.json")


if __name__ == "__main__":
    main()
