
# import zipfile
# import io
#         # Determinar el nombre del archivo y tipo de contenido
#         if file_type == 'xlsx':
#             filename = f'{safe_title}_{timestamp}.xlsx'
#             content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
#         elif file_type == 'json':
#             filename = f'{safe_title}_{timestamp}.json'
#             content_type = 'application/json'
#         elif file_type == 'html':
#             filename = f'{safe_title}_{timestamp}.html'
#             content_type = 'text/html'
#         elif file_type == 'csv':
#             filename = f'{safe_title}_{timestamp}.csv'
#             content_type = 'text/csv'
#         else:
#             # Default to CSV if the file_type is unknown
#             filename = f'{safe_title}_{timestamp}.csv'
#             content_type = 'text/csv'

#         # Si se requiere zip, comprimir el archivo
#         if zip_option.lower() == 'yes':
#             zip_filename = f'{filename}.zip'
#             zip_buffer = io.BytesIO()
#             with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
#                 zip_file.writestr(filename, reporte_data)

#             zip_buffer.seek(0)
#             response = make_response(zip_buffer.read())
#             response.headers['Content-Type'] = 'application/zip'
#             response.headers['Content-Disposition'] = f'attachment; filename={zip_filename}'
#         else:
#             # Si no se requiere zip, simplemente devolver el archivo original
#             response = make_response(reporte_data)
#             response.headers['Content-Type'] = content_type
#             response.headers['Content-Disposition'] = f'attachment; filename={filename}'

#         return response, 200
#     else:
#         logger.info("El util>obtener_reporte no devolvió la data...Respuesta de server 404")
#         return jsonify({"error": "No se encontró el reporte"}), 404
# DESCOMENTAR LA TOTALIDAD Y COLOCAR AL FINAL DE LA RUTA DE RECUPERACION SI LO NECESITAMOS.
# RECORDAR AGREGAR PROP "zip": "yes"/"no" en los pedidos si se agrega esto nuevamente ( igual no es  obligatorio)