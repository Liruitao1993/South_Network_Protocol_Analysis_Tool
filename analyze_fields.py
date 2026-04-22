import frame_generator_schema as s

with open('current_fields_report.txt', 'w', encoding='utf-8') as out:
    for di, meta in sorted(s.DI_FIELD_SCHEMA.items()):
        fields = meta.get('fields', [])
        di_str = f'{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}'
        name = meta['name']
        if fields:
            out.write(f'{di_str} {name}: {len(fields)} fields\n')
            for f in fields:
                out.write(f'    {f}\n')
        else:
            out.write(f'{di_str} {name}: NO FIELDS (no data unit)\n')

print('Report written to current_fields_report.txt')
