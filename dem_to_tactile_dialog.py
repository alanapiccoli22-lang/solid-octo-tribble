# -*- coding: utf-8 -*-

import os
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtWidgets import QDialog, QComboBox, QDoubleSpinBox, QMessageBox

from qgis.core import QgsProject, QgsMapLayerProxyModel, QgsRectangle, Qgis
from qgis.gui import QgsMapLayerComboBox

# Carregar dinamicamente o arquivo UI do Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'dem_to_tactile_dialog_base.ui'))


class DemToTactileDialog(QDialog, FORM_CLASS):
    """Controlador da Interface Gráfica do Plugin DEM to Tactile 3D."""

    def __init__(self, iface, parent=None):
        """Inicializa o diálogo do plugin.

        :param iface: Interface do QGIS (QgisInterface) para interações com o sistema.  # noqa: E501
        """
        super(DemToTactileDialog, self).__init__(parent)
        self.setupUi(self)
        self.iface = iface

        # Configurar filtros para os seletores de camada nativos do QGIS
        self.mRasterLayerComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)

        # Configurar widget de extensão do QGIS
        self.mExtentWidget.setOriginalExtent(
            QgsRectangle(), QgsProject.instance().crs())
        self.mExtentWidget.setCurrentExtent(
            QgsRectangle(), QgsProject.instance().crs())
        self.mExtentWidget.setOutputExtentFromOriginal()

        # Conectar sinal de mudança de camada raster para atualizar a extensão
        # padrão
        self.mRasterLayerComboBox.layerChanged.connect(
            self.on_raster_layer_changed)

        # Inicializar tabela de vetores
        self.setup_vector_table()

        # Conectar botões da interface
        self.mAddVectorButton.clicked.connect(self.add_vector_row)
        self.mRemoveVectorButton.clicked.connect(self.remove_selected_row)
        self.mGenerateButton.clicked.connect(self.on_generate_clicked)

        # Configurar valor inicial da extensão se já houver um raster ativo
        self.on_raster_layer_changed(self.mRasterLayerComboBox.currentLayer())

        # Carregar e exibir as logos na aba "Sobre" (Geolab e a startup
        # AnthropicGeo)
        from qgis.PyQt.QtGui import QPixmap
        logo_geolab_path = os.path.join(
            os.path.dirname(__file__), 'logo_geolab.jpg')
        if os.path.exists(logo_geolab_path):
            self.labelLogo.setPixmap(QPixmap(logo_geolab_path))

        logo_anthropic_path = os.path.join(
            os.path.dirname(__file__), 'logo_anthropic.png')
        if os.path.exists(logo_anthropic_path):
            self.labelLogoAnthropic.setPixmap(QPixmap(logo_anthropic_path))

    def setup_vector_table(self):
        """Configura o layout e comportamento inicial da tabela de vetores."""
        self.mVectorTable.setColumnCount(4)
        self.mVectorTable.setHorizontalHeaderLabels([
            "Camada Vetorial", "Efeito Tátil", "Buffer (Metros)", "Altura/Prof. (mm)"  # noqa: E501
        ])
        # Compatibilidade cruzada PyQt5 / PyQt6 para os enums do Qt
        from qgis.PyQt.QtWidgets import QHeaderView, QAbstractItemView

        if hasattr(QHeaderView, 'ResizeMode'):
            stretch_mode = QHeaderView.ResizeMode.Stretch
            contents_mode = QHeaderView.ResizeMode.ResizeToContents
        else:
            stretch_mode = QHeaderView.Stretch
            contents_mode = QHeaderView.ResizeToContents

        if hasattr(QAbstractItemView, 'SelectionBehavior'):
            select_rows = QAbstractItemView.SelectionBehavior.SelectRows
        else:
            select_rows = QAbstractItemView.SelectRows

        if hasattr(QAbstractItemView, 'SelectionMode'):
            single_selection = QAbstractItemView.SelectionMode.SingleSelection
        else:
            single_selection = QAbstractItemView.SingleSelection

        # Ajustar modo de redimensionamento das colunas
        header = self.mVectorTable.horizontalHeader()
        header.setSectionResizeMode(0, stretch_mode)
        header.setSectionResizeMode(1, contents_mode)
        header.setSectionResizeMode(2, contents_mode)
        header.setSectionResizeMode(3, contents_mode)

        self.mVectorTable.setSelectionBehavior(select_rows)
        self.mVectorTable.setSelectionMode(single_selection)

    def on_raster_layer_changed(self, layer):
        """Atualiza a extensão sugerida no widget de extensão ao trocar o raster.  # noqa: E501

        :param layer: A nova camada raster selecionada.
        """
        if layer:
            self.mExtentWidget.setOriginalExtent(layer.extent(), layer.crs())
            self.mExtentWidget.setCurrentExtent(layer.extent(), layer.crs())
            self.mExtentWidget.setOutputExtentFromOriginal()

            # Auto-preencher dimensões físicas baseadas no aspect ratio do
            # raster
            extent = layer.extent()
            if extent.width() > 0 and extent.height() > 0:
                ratio = extent.height() / extent.width()
                current_width = self.mWidthSpinBox.value()
                # Ajusta a altura mantendo a proporção do relevo real
                self.mHeightSpinBox.setValue(current_width * ratio)

    def add_vector_row(self):
        """Adiciona uma nova linha de configuração de camada vetorial na tabela."""  # noqa: E501
        row_idx = self.mVectorTable.rowCount()
        self.mVectorTable.insertRow(row_idx)

        # Coluna 0: Seletor de Camada Vetorial do QGIS
        layer_combo = QgsMapLayerComboBox()
        layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.mVectorTable.setCellWidget(row_idx, 0, layer_combo)

        # Coluna 1: Seletor de Efeito Tátil
        effect_combo = QComboBox()
        effect_combo.addItems([
            "Extrudado (Positivo)",
            "Escavado (Negativo)",
            "Lago/Massa d'Água (Nivelado Fixo)",
            "Lago/Massa d'Água (Offset Negativo)"
        ])
        self.mVectorTable.setCellWidget(row_idx, 1, effect_combo)

        # Coluna 2: Largura do Buffer em metros
        buffer_spin = QDoubleSpinBox()
        buffer_spin.setRange(0.0, 50000.0)
        buffer_spin.setSingleStep(5.0)
        # 15 metros de buffer padrão para trilhas/rios
        buffer_spin.setValue(15.0)
        self.mVectorTable.setCellWidget(row_idx, 2, buffer_spin)

        # Coluna 3: Altura/Profundidade do relevo em mm físicos da maquete
        height_spin = QDoubleSpinBox()
        height_spin.setRange(-500.0, 500.0)
        height_spin.setSingleStep(0.2)
        height_spin.setValue(1.0)  # 1.0 mm de altura padrão
        self.mVectorTable.setCellWidget(row_idx, 3, height_spin)

        # Conectar mudanças nos seletores
        effect_combo.currentIndexChanged.connect(
            lambda idx, r=row_idx: self.on_effect_changed(r, idx))
        layer_combo.layerChanged.connect(
            lambda layer, r=row_idx: self.on_row_layer_changed(r, layer))

        # Disparar configuração inicial da linha
        self.on_row_layer_changed(row_idx, layer_combo.currentLayer())

    def on_row_layer_changed(self, row, layer):
        """Ajusta a linha com base no tipo de geometria da camada (Linha vs Polígono)."""  # noqa: E501
        effect_combo = self.mVectorTable.cellWidget(row, 1)
        buffer_spin = self.mVectorTable.cellWidget(row, 2)
        height_spin = self.mVectorTable.cellWidget(row, 3)

        if not layer or not layer.isValid(
        ) or not effect_combo or not buffer_spin or not height_spin:
            return

        geom_type = layer.geometryType()

        # Se for Polígono (geometryType == 2)
        if geom_type == 2:
            # Polígonos representam áreas fechadas (como lagos/lagoas) e não
            # precisam de buffer linear
            buffer_spin.setValue(0.0)
            buffer_spin.setEnabled(False)

            # Se for polígono, pre-selecionar o efeito de Massa d'Água Nivelada
            # se não estiver selecionado
            current_effect = effect_combo.currentText()
            if "Lago/Massa" not in current_effect:
                # Lago/Massa d'Água (Nivelado Fixo)
                effect_combo.setCurrentIndex(2)
        else:
            # Se for Linha/Ponto, permitir buffer
            # Só desabilitar se o efeito for de Massa d'Água (índices 2 ou 3)
            effect_idx = effect_combo.currentIndex()
            if effect_idx in (2, 3):
                buffer_spin.setValue(0.0)
                buffer_spin.setEnabled(False)
            else:
                buffer_spin.setEnabled(True)
                if buffer_spin.value() == 0:
                    buffer_spin.setValue(15.0)

    def on_effect_changed(self, row, effect_idx):
        """Ajusta os spinboxes da linha quando o tipo de efeito é alterado.

        :param row: Índice da linha editada.
        :param effect_idx: Índice do efeito selecionado na combo.
        """
        layer_combo = self.mVectorTable.cellWidget(row, 0)
        buffer_spin = self.mVectorTable.cellWidget(row, 2)
        height_spin = self.mVectorTable.cellWidget(row, 3)

        if not buffer_spin or not height_spin:
            return

        # Verificar o tipo de geometria da camada ativa na linha
        is_polygon = False
        if layer_combo and layer_combo.currentLayer():
            is_polygon = (layer_combo.currentLayer().geometryType() == 2)

        # Ajustar habilitação do buffer
        if is_polygon or effect_idx in (2, 3):
            buffer_spin.setValue(0.0)
            buffer_spin.setEnabled(False)
        else:
            buffer_spin.setEnabled(True)
            if buffer_spin.value() == 0:
                buffer_spin.setValue(15.0)

        # Ajustar faixas de valores de altura conforme o efeito
        if effect_idx == 2:  # Nivelado Fixo
            height_spin.setValue(0.0)
            height_spin.setRange(-10.0, 500.0)
        elif effect_idx == 3:  # Offset Negativo
            height_spin.setValue(1.5)
            height_spin.setRange(0.1, 50.0)
        else:  # Extrudado / Escavado
            height_spin.setValue(1.0)
            height_spin.setRange(0.1, 50.0)

    def remove_selected_row(self):
        """Remove a linha de vetor selecionada pelo usuário."""
        selected_ranges = self.mVectorTable.selectedRanges()
        if selected_ranges:
            row = selected_ranges[0].topRow()
            self.mVectorTable.removeRow(row)
        else:
            QMessageBox.warning(
                self,
                "Aviso",
                "Por favor, selecione uma linha da tabela para remover.")

    def on_generate_clicked(self):
        """Valida as opções da interface e inicia a geração do modelo STL."""
        # 1. Validar camada raster
        raster_layer = self.mRasterLayerComboBox.currentLayer()
        if not raster_layer:
            QMessageBox.critical(
                self, "Erro", "Selecione uma Camada Raster (MDE) válida.")
            return

        # 2. Validar extensão
        extent = self.mExtentWidget.outputExtent()
        if extent.isEmpty():
            QMessageBox.critical(
                self, "Erro", "A extensão de recorte selecionada é inválida ou está vazia.")  # noqa: E501
            return

        # 3. Validar dimensões físicas
        width_mm = self.mWidthSpinBox.value()
        height_mm = self.mHeightSpinBox.value()
        res_mm = self.mResSpinBox.value()

        if width_mm <= 0 or height_mm <= 0 or res_mm <= 0:
            QMessageBox.critical(
                self,
                "Erro",
                "As dimensões e a resolução do modelo devem ser maiores que zero.")  # noqa: E501
            return

        # 4. Validar arquivo de destino
        output_file = self.mFileWidget.filePath()
        if not output_file:
            QMessageBox.critical(
                self, "Erro", "Selecione um local e nome de arquivo STL para salvar.")  # noqa: E501
            return

        # 5. Coletar configurações das camadas vetoriais
        vector_settings = []
        for row in range(self.mVectorTable.rowCount()):
            layer_combo = self.mVectorTable.cellWidget(row, 0)
            effect_combo = self.mVectorTable.cellWidget(row, 1)
            buffer_spin = self.mVectorTable.cellWidget(row, 2)
            height_spin = self.mVectorTable.cellWidget(row, 3)

            if layer_combo and layer_combo.currentLayer():
                vector_settings.append({
                    'layer': layer_combo.currentLayer(),
                    'effect': effect_combo.currentText(),
                    'buffer_m': buffer_spin.value(),
                    'height_mm': height_spin.value()
                })

        # Desabilitar botão de gerar para evitar duplo clique
        self.mGenerateButton.setEnabled(False)
        self.mProgressBar.setValue(0)

        # Importar processador geométrico
        from .dem_to_tactile_processor import DemToTactileProcessor
        processor = DemToTactileProcessor()

        # Função callback para atualização de progresso
        def progress_updater(percent, status_str):
            self.mProgressBar.setValue(percent)
            # Exibir na barra de status do QGIS
            self.iface.messageBar().pushMessage(
                "DEM to Tactile 3D", status_str, level=Qgis.Info, duration=1
            )
            # Forçar atualização visual do Qt
            QtWidgets.QApplication.processEvents()

        # Executar processamento (bloqueante mas com processEvents para manter
        # a UI viva)
        try:
            success = processor.run(
                raster_layer=raster_layer,
                extent=extent,
                model_width_mm=width_mm,
                model_height_mm=height_mm,
                resolution_mm=res_mm,
                base_height_m=self.mBaseHeightSpinBox.value(),
                exaggeration=self.mExaggerationSpinBox.value(),
                vector_settings=vector_settings,
                output_path=output_file,
                progress_callback=progress_updater
            )

            if success:
                QMessageBox.information(
                    self, "Sucesso",
                    f"Modelo 3D tátil gerado com sucesso!\nSalvo em: {output_file}"  # noqa: E501
                )
                self.iface.messageBar().pushSuccess(
                    "DEM to Tactile 3D", f"Modelo STL salvo com sucesso em {output_file}")  # noqa: E501
            else:
                QMessageBox.critical(
                    self,
                    "Erro",
                    "Ocorreu um erro durante o processamento geométrico. Verifique os logs.")  # noqa: E501
        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Ocorreu uma exceção inesperada durante a geração:\n{str(e)}"
            )
        finally:
            self.mGenerateButton.setEnabled(True)
            self.mProgressBar.setValue(100 if success else 0)
