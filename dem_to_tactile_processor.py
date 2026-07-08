# -*- coding: utf-8 -*-

import os
import math
import struct
import numpy as np

from qgis.core import (
    QgsProject,
    QgsPointXY,
    QgsGeometry,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsFeatureRequest,
    QgsSpatialIndex
)

class DemToTactileProcessor:
    """Motor de processamento geométrico para geração de modelos táteis 3D (STL)."""

    def __init__(self):
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self, raster_layer, extent, model_width_mm, model_height_mm,
            resolution_mm, base_height_m, exaggeration, vector_settings,
            output_path, progress_callback=None):
        """Executa o processamento completo e gera o arquivo STL.

        :param raster_layer: QgsRasterLayer contendo o MDE.
        :param extent: QgsRectangle definindo a área de recorte.
        :param model_width_mm: Largura física do modelo em mm.
        :param model_height_mm: Altura física do modelo em mm.
        :param resolution_mm: Tamanho do pixel/grade no modelo físico em mm (ex: 0.5).
        :param base_height_m: Cota de elevação correspondente à base do bloco (Z=0) em metros.
        :param exaggeration: Fator de exagero vertical (ex: 1.5).
        :param vector_settings: Lista de dicionários com chaves:
                                ['layer', 'effect', 'buffer_m', 'height_mm']
        :param output_path: Caminho completo para o arquivo STL de destino.
        :param progress_callback: Função callback(percent_int, status_str) para atualizar a UI.
        """
        self.is_cancelled = False

        def report_progress(percent, status_str):
            if progress_callback:
                progress_callback(percent, status_str)

        report_progress(5, "Iniciando processamento e preparando grade...")

        # 1. Configurar extensões e resolução da grade
        x_min, x_max = extent.xMinimum(), extent.xMaximum()
        y_min, y_max = extent.yMinimum(), extent.yMaximum()
        width_geo = x_max - x_min
        height_geo = y_max - y_min

        # Dimensões da grade em pixels/células
        cols = max(2, int(model_width_mm / resolution_mm))
        rows = max(2, int(model_height_mm / resolution_mm))

        cell_size_x_geo = width_geo / cols
        cell_size_y_geo = height_geo / rows

        # Fatores de escala
        # scale_xy: escala horizontal adimensional (metros de terreno por metro de modelo)
        scale_xy = width_geo / (model_width_mm / 1000.0)
        # scale_z: metros de terreno por milímetro de modelo físico (multiplica por 1000 para converter M para MM)
        scale_z = scale_xy / (1000.0 * exaggeration)

        # Inicializar grade de alturas (em metros de terreno)
        grid_z = np.zeros((rows, cols), dtype=np.float32)

        report_progress(10, "Amostrando dados de elevação do MDE...")

        # 2. Amostragem do Raster (Resampling)
        provider = raster_layer.dataProvider()
        no_data_value = provider.sourceNoDataValue(1)

        # Amostragem direta célula por célula
        for r in range(rows):
            if self.is_cancelled:
                return False

            # Atualizar progresso da amostragem (entre 10% e 40%)
            if r % max(1, rows // 10) == 0:
                percent = 10 + int(30 * (r / rows))
                report_progress(percent, f"Amostrando MDE: linha {r}/{rows}...")

            # Coordenada Y geográfica do centro da célula
            y_geo = y_max - (r + 0.5) * cell_size_y_geo

            for c in range(cols):
                # Coordenada X geográfica do centro da célula
                x_geo = x_min + (c + 0.5) * cell_size_x_geo

                val, ok = provider.sample(QgsPointXY(x_geo, y_geo), 1)
                if ok and val != no_data_value and not math.isnan(val):
                    grid_z[r, c] = val
                else:
                    grid_z[r, c] = base_height_m

        # Converter a grade para milímetros do modelo físico
        grid_z_model = (grid_z - base_height_m) / scale_z
        # Garantir espessura mínima de segurança (0.2 mm) para não rasgar a base
        grid_z_model = np.clip(grid_z_model, 0.2, None)

        # 3. Processar Sobreposições Vetoriais
        report_progress(45, "Preparando processamento das camadas vetoriais...")

        raster_crs = raster_layer.crs()
        project = QgsProject.instance()

        for idx, setting in enumerate(vector_settings):
            layer = setting['layer']
            effect = setting['effect']
            buffer_m = setting['buffer_m']
            height_mm = setting['height_mm']

            if not layer or not layer.isValid():
                continue

            status_msg = f"Processando vetor {idx+1}/{len(vector_settings)}: {layer.name()}..."
            report_progress(45 + int(15 * (idx / len(vector_settings))), status_msg)

            # Criar transformador de coordenadas se o CRS for diferente
            transform = None
            if layer.crs() != raster_crs:
                transform = QgsCoordinateTransform(layer.crs(), raster_crs, project)

            # Requisitar feições. Se houver transformação, precisamos projetar a extensão geográfica do MDE
            # de volta para o CRS do vetor para que o filtro espacial de feições funcione perfeitamente!
            request = QgsFeatureRequest()
            if transform:
                try:
                    inverse_transform = QgsCoordinateTransform(raster_crs, layer.crs(), project)
                    vector_extent = inverse_transform.transformBoundingBox(extent)
                    request.setFilterRect(vector_extent)
                except Exception:
                    request.setFilterRect(extent)
            else:
                request.setFilterRect(extent)

            features = list(layer.getFeatures(request))

            if not features:
                continue

            is_line = (layer.geometryType() == 1) # 1 = LineGeometry
            is_polygon = (layer.geometryType() == 2) # 2 = PolygonGeometry

            # Para cada feição vetorial intersectando a área, aplicamos a deformação localmente
            # usando a otimização de bounding box para máxima performance em Python (sem indexar todo pixel)
            for f in features:
                geom = f.geometry()
                if not geom or geom.isEmpty():
                    continue

                if transform:
                    geom.transform(transform)

                # Obter a versão da geometria de busca (com buffer para linhas, a própria para polígonos)
                if is_line and buffer_m > 0:
                    search_geom = geom.buffer(buffer_m, 3)
                else:
                    search_geom = geom

                if not search_geom or search_geom.isEmpty():
                    continue

                # Obter o bounding box da geometria de busca e intersectar com a extensão de recorte do MDE
                bbox = search_geom.boundingBox()
                bbox_intersect = bbox.intersect(extent)

                if bbox_intersect.isEmpty():
                    continue

                # Converter coordenadas geográficas da caixa envolvente em índices da grade (r_start a r_end, c_start a c_end)
                c_start = max(0, int((bbox_intersect.xMinimum() - x_min) / cell_size_x_geo))
                c_end = min(cols - 1, int((bbox_intersect.xMaximum() - x_min) / cell_size_x_geo) + 1)

                r_start = max(0, int((y_max - bbox_intersect.yMaximum()) / cell_size_y_geo))
                r_end = min(rows - 1, int((y_max - bbox_intersect.yMinimum()) / cell_size_y_geo) + 1)

                # Loop restrito apenas aos pixels dentro da caixa envolvente da feição
                for r in range(r_start, r_end + 1):
                    if r >= rows:
                        continue
                    y_geo = y_max - (r + 0.5) * cell_size_y_geo

                    for c in range(c_start, c_end + 1):
                        if c >= cols:
                            continue
                        x_geo = x_min + (c + 0.5) * cell_size_x_geo

                        pt = QgsPointXY(x_geo, y_geo)
                        pt_geom = QgsGeometry.fromPointXY(pt)

                        if is_polygon:
                            if search_geom.contains(pt_geom):
                                current_z = grid_z_model[r, c]
                                if "Nivelado Fixo" in effect:
                                    grid_z_model[r, c] = height_mm
                                elif "Offset Negativo" in effect:
                                    grid_z_model[r, c] = max(0.2, current_z - height_mm)
                                elif "Extrudado (Positivo)" in effect:
                                    grid_z_model[r, c] = current_z + height_mm
                                elif "Escavado (Negativo)" in effect:
                                    grid_z_model[r, c] = max(0.2, current_z - height_mm)

                        elif is_line:
                            if search_geom.contains(pt_geom):
                                d = geom.distance(pt_geom)
                                if d <= buffer_m:
                                    # Fator de perfil arredondado (cosseno)
                                    factor = (1.0 + math.cos(math.pi * (d / buffer_m))) / 2.0

                                    current_z = grid_z_model[r, c]
                                    if effect == "Extrudado (Positivo)":
                                        grid_z_model[r, c] = max(current_z, current_z + height_mm * factor)
                                    elif effect == "Escavado (Negativo)":
                                        grid_z_model[r, c] = min(current_z, max(0.2, current_z - height_mm * factor))

        report_progress(60, "Grade de relevo concluída. Iniciando triangulação da malha 3D...")

        # 4. Geração de Triângulos (Malha Sólida)
        # Reservar listas de triângulos para gravação em lote
        # Cada triângulo é armazenado como (normal_x, normal_y, normal_z, v1, v2, v3)
        # onde v1, v2, v3 são tuplas (x, y, z) em mm do modelo físico
        triangles = []

        # Espaçamento em mm
        dx = resolution_mm
        dy = resolution_mm

        # Função auxiliar para calcular normal simples (opcional, slicers recalculam)
        def get_normal(p1, p2, p3):
            # Vetores u e v
            ux, uy, uz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
            vx, vy, vz = p3[0]-p1[0], p3[1]-p1[1], p3[2]-p1[2]
            # Produto vetorial u x v
            nx = uy*vz - uz*vy
            ny = uz*vx - ux*vz
            nz = ux*vy - uy*vx
            length = math.sqrt(nx*nx + ny*ny + nz*nz)
            if length > 0:
                return (nx/length, ny/length, nz/length)
            return (0.0, 0.0, 1.0)

        # 4.1 Triangular Superfície Superior (Top)
        # X cresce para a direita (colunas c), Y cresce para cima (linhas r decrescentes)
        # Mapeamento físico:
        # x_phys = c * dx
        # y_phys = (rows - 1 - r) * dy
        for r in range(rows - 1):
            if self.is_cancelled:
                return False

            if r % max(1, rows // 10) == 0:
                percent = 60 + int(20 * (r / rows))
                report_progress(percent, f"Triangulando superfície: linha {r}/{rows}...")

            y_top = (rows - 1 - r) * dy
            y_bot = (rows - 1 - (r + 1)) * dy

            for c in range(cols - 1):
                x_left = c * dx
                x_right = (c + 1) * dx

                # Quatro cantos da célula
                v_tl = (x_left, y_top, grid_z_model[r, c])
                v_tr = (x_right, y_top, grid_z_model[r, c+1])
                v_bl = (x_left, y_bot, grid_z_model[r+1, c])
                v_br = (x_right, y_bot, grid_z_model[r+1, c+1])

                # Triângulo 1: TL -> BL -> TR (normal apontando para cima)
                n1 = get_normal(v_tl, v_bl, v_tr)
                triangles.append((n1, v_tl, v_bl, v_tr))

                # Triângulo 2: TR -> BL -> BR (normal apontando para cima)
                n2 = get_normal(v_tr, v_bl, v_br)
                triangles.append((n2, v_tr, v_bl, v_br))

        # 4.2 Triangular Base Inferior (Bottom, Z = 0, apontando para baixo)
        for r in range(rows - 1):
            y_top = (rows - 1 - r) * dy
            y_bot = (rows - 1 - (r + 1)) * dy
            for c in range(cols - 1):
                x_left = c * dx
                x_right = (c + 1) * dx

                v_tl = (x_left, y_top, 0.0)
                v_tr = (x_right, y_top, 0.0)
                v_bl = (x_left, y_bot, 0.0)
                v_br = (x_right, y_bot, 0.0)

                # Inverter ordem para normal apontar para baixo (-Z)
                # Triângulo 1: TL -> TR -> BL
                n1 = (0.0, 0.0, -1.0)
                triangles.append((n1, v_tl, v_tr, v_bl))

                # Triângulo 2: TR -> BR -> BL
                n2 = (0.0, 0.0, -1.0)
                triangles.append((n2, v_tr, v_br, v_bl))

        # 4.3 Parede Lateral Esquerda (c = 0, normal aponta para -X)
        for r in range(rows - 1):
            y_top = (rows - 1 - r) * dy
            y_bot = (rows - 1 - (r + 1)) * dy

            v_t_top = (0.0, y_top, grid_z_model[r, 0])
            v_t_bot = (0.0, y_bot, grid_z_model[r+1, 0])
            v_b_top = (0.0, y_top, 0.0)
            v_b_bot = (0.0, y_bot, 0.0)

            # Triângulo 1: v_t_top -> v_b_top -> v_t_bot
            n1 = (-1.0, 0.0, 0.0)
            triangles.append((n1, v_t_top, v_b_top, v_t_bot))

            # Triângulo 2: v_t_bot -> v_b_top -> v_b_bot
            n2 = (-1.0, 0.0, 0.0)
            triangles.append((n2, v_t_bot, v_b_top, v_b_bot))

        # 4.4 Parede Lateral Direita (c = cols - 1, normal aponta para +X)
        w_phys = (cols - 1) * dx
        for r in range(rows - 1):
            y_top = (rows - 1 - r) * dy
            y_bot = (rows - 1 - (r + 1)) * dy

            v_t_top = (w_phys, y_top, grid_z_model[r, cols - 1])
            v_t_bot = (w_phys, y_bot, grid_z_model[r+1, cols - 1])
            v_b_top = (w_phys, y_top, 0.0)
            v_b_bot = (w_phys, y_bot, 0.0)

            # Triângulo 1: v_t_top -> v_t_bot -> v_b_top
            n1 = (1.0, 0.0, 0.0)
            triangles.append((n1, v_t_top, v_t_bot, v_b_top))

            # Triângulo 2: v_t_bot -> v_b_bot -> v_b_top
            n2 = (1.0, 0.0, 0.0)
            triangles.append((n2, v_t_bot, v_b_bot, v_b_top))

        # 4.5 Parede Lateral Superior (r = 0, normal aponta para +Y)
        h_phys = (rows - 1) * dy
        for c in range(cols - 1):
            x_left = c * dx
            x_right = (c + 1) * dx

            v_t_left = (x_left, h_phys, grid_z_model[0, c])
            v_t_right = (x_right, h_phys, grid_z_model[0, c+1])
            v_b_left = (x_left, h_phys, 0.0)
            v_b_right = (x_right, h_phys, 0.0)

            # Triângulo 1: v_t_left -> v_t_right -> v_b_left
            n1 = (0.0, 1.0, 0.0)
            triangles.append((n1, v_t_left, v_t_right, v_b_left))

            # Triângulo 2: v_t_right -> v_b_right -> v_b_left
            n2 = (0.0, 1.0, 0.0)
            triangles.append((n2, v_t_right, v_b_right, v_b_left))

        # 4.6 Parede Lateral Inferior (r = rows - 1, normal aponta para -Y)
        for c in range(cols - 1):
            x_left = c * dx
            x_right = (c + 1) * dx

            v_t_left = (x_left, 0.0, grid_z_model[rows - 1, c])
            v_t_right = (x_right, 0.0, grid_z_model[rows - 1, c+1])
            v_b_left = (x_left, 0.0, 0.0)
            v_b_right = (x_right, 0.0, 0.0)

            # Triângulo 1: v_t_left -> v_b_left -> v_t_right
            n1 = (0.0, -1.0, 0.0)
            triangles.append((n1, v_t_left, v_b_left, v_t_right))

            # Triângulo 2: v_t_right -> v_b_left -> v_b_right
            n2 = (0.0, -1.0, 0.0)
            triangles.append((n2, v_t_right, v_b_left, v_b_right))

        report_progress(85, "Escrevendo arquivo STL binário...")

        # 5. Escrever o arquivo STL binário de forma extremamente rápida e robusta
        try:
            # Garantir que a pasta de destino existe
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            num_triangles = len(triangles)

            with open(output_path, 'wb') as f:
                # 80 bytes de cabeçalho
                header = b'DEM to Tactile 3D Plugin - Watertight Solid STL Output'
                header = header.ljust(80, b' ')
                f.write(header)

                # 4 bytes com o número de triângulos (unsigned integer)
                f.write(struct.pack('<I', num_triangles))

                # Gravar cada triângulo em lote para melhor performance
                # Cada triângulo tem: 3 floats (normal) + 9 floats (vértices) + 2 bytes (attribute byte count)
                # Total por triângulo: 50 bytes
                fmt = '<ffffffffffffH'
                for t in triangles:
                    normal, v1, v2, v3 = t
                    data = struct.pack(fmt,
                                       normal[0], normal[1], normal[2],
                                       v1[0], v1[1], v1[2],
                                       v2[0], v2[1], v2[2],
                                       v3[0], v3[1], v3[2],
                                       0) # Attribute byte count
                    f.write(data)

            report_progress(100, f"Modelo gerado com sucesso em: {output_path}")
            return True

        except Exception as e:
            report_progress(100, f"Erro ao salvar arquivo STL: {str(e)}")
            return False
