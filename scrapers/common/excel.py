import xlsxwriter


def salvar_planilha(data: list, arquivo_caminho: str, lote_numero: str, raspar_descricao: bool = False) -> None:
    """Gera o arquivo .xlsx padrão do NAVI com formatação e cálculo de preço unitário."""
    workbook  = xlsxwriter.Workbook(arquivo_caminho)
    worksheet = workbook.add_worksheet()

    title_format   = workbook.add_format({'text_wrap': True, 'align': 'left',   'valign': 'vcenter'})
    center_format  = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
    vcenter_format = workbook.add_format({'valign': 'vcenter'})
    desc_format    = workbook.add_format({'text_wrap': True, 'align': 'left', 'valign': 'top'})
    header_format  = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
    number_format  = workbook.add_format({'num_format': '#,##0.00', 'align': 'center', 'valign': 'vcenter'})

    if raspar_descricao:
        headers = [
            'ID', 'Lote', 'Endereço', 'Preço',
            'Área Construída (m²)', 'Área Terreno (m²)', 'Preço Unit. (R$/m²)',
            'Quartos', 'Banheiros', 'Vagas de Garagem', 'Descrição', 'Link',
        ]
        col_widths = [10, 10, 35, 15, 18, 18, 18, 10, 12, 18, 50, 10]
        col_fmts   = [
            center_format, center_format, title_format, center_format,
            center_format, center_format, center_format,
            center_format, center_format, center_format, desc_format, vcenter_format,
        ]
    else:
        headers = [
            'ID', 'Lote', 'Endereço', 'Preço', 'Área (m²)', 'Preço Unit. (R$/m²)',
            'Quartos', 'Banheiros', 'Vagas de Garagem', 'Link',
        ]
        col_widths = [10, 10, 35, 15, 15, 18, 10, 12, 18, 10]
        col_fmts   = [
            center_format, center_format, title_format, center_format,
            center_format, center_format,
            center_format, center_format, center_format, vcenter_format,
        ]

    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    for col, (width, fmt) in enumerate(zip(col_widths, col_fmts)):
        col_letter = chr(ord('A') + col)
        worksheet.set_column(f'{col_letter}:{col_letter}', width, fmt)

    for row, entry in enumerate(data, 1):
        worksheet.write(row, 0, entry['ID'])
        worksheet.write(row, 1, int(lote_numero))
        worksheet.write(row, 2, entry['Endereço'])
        worksheet.write(row, 3, entry['Preço'])

        if raspar_descricao:
            area_construida = entry.get('Área Construída (m²)')
            area_terreno    = entry.get('Área Terreno (m²)')

            worksheet.write(row, 4, area_construida if area_construida is not None else '-')
            worksheet.write(row, 5, area_terreno    if area_terreno    is not None else '-')

            try:
                preco_float = float(''.join(filter(str.isdigit, str(entry['Preço']))))
                area_float  = float(area_construida) if area_construida else 0
                preco_unit  = preco_float / area_float if area_float > 0 else 0
                worksheet.write_number(row, 6, preco_unit, number_format)
            except Exception:
                worksheet.write(row, 6, '-')

            worksheet.write(row, 7,  entry['Quartos'])
            worksheet.write(row, 8,  entry['Banheiros'])
            worksheet.write(row, 9,  entry['Vagas de Garagem'])
            worksheet.write(row, 10, entry.get('Descrição', ''))

            link = str(entry['Link'])
            if link.startswith('http'):
                worksheet.write_url(row, 11, link, vcenter_format)
            else:
                worksheet.write(row, 11, 'Link não disponível', vcenter_format)
        else:
            worksheet.write(row, 4, entry['Área (m²)'])

            try:
                preco_float = float(''.join(filter(str.isdigit, str(entry['Preço']))))
                area_val    = entry['Área (m²)']
                area_float  = float(area_val) if area_val and area_val != '-' else 0
                preco_unit  = preco_float / area_float if area_float > 0 else 0
                worksheet.write_number(row, 5, preco_unit, number_format)
            except Exception:
                worksheet.write(row, 5, '-')

            worksheet.write(row, 6, entry['Quartos'])
            worksheet.write(row, 7, entry['Banheiros'])
            worksheet.write(row, 8, entry['Vagas de Garagem'])

            link = str(entry['Link'])
            if link.startswith('http'):
                worksheet.write_url(row, 9, link, vcenter_format)
            else:
                worksheet.write(row, 9, 'Link não disponível', vcenter_format)

    workbook.close()
    print(f"Planilha {arquivo_caminho} gerada com sucesso!")
