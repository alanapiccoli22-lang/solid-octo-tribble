# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

# Importar o diálogo do plugin
from .dem_to_tactile_dialog import DemToTactileDialog

class DemToTactilePlugin:
    """Classe principal de integração do QGIS para o plugin DEM to Tactile 3D."""

    def __init__(self, iface):
        """Inicializa o plugin com a interface do QGIS.
        
        :param iface: Instância da QgisInterface do QGIS.
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
        # Referência ao diálogo principal
        self.dialog = None
        
        # Elementos da interface gráfica do QGIS
        self.action = None
        self.menu_title = "DEM to Tactile 3D"

    def initGui(self):
        """Inicializa os elementos de interface gráfica do plugin no QGIS."""
        # Caminho para o ícone
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        icon = QIcon(icon_path)
        
        # Criar a Ação do QGIS
        self.action = QAction(
            icon,
            "Gerar Modelo 3D Tátil...",
            self.iface.mainWindow()
        )
        self.action.setStatusTip("Transforma um MDE e vetores em um modelo 3D tátil fechado (STL)")
        self.action.setWhatsThis("Plugin para geração de modelos físicos 3D táteis a partir de relevo raster e vetores.")
        self.action.triggered.connect(self.run)
        
        # Adicionar ao menu 'Raster' do QGIS
        self.iface.addPluginToRasterMenu(self.menu_title, self.action)
        
        # Adicionar à barra de ferramentas 'Raster' do QGIS
        self.iface.addRasterToolBarIcon(self.action)

    def unload(self):
        """Remove os elementos de interface criados pelo plugin ao desativá-lo."""
        if self.action:
            # Remover do menu 'Raster'
            self.iface.removePluginRasterMenu(self.menu_title, self.action)
            # Remover da barra de ferramentas
            self.iface.removeRasterToolBarIcon(self.action)
            
        # Destruir o diálogo se ele existir
        if self.dialog:
            self.dialog.deleteLater()
            self.dialog = None

    def run(self):
        """Executa a rotina principal do plugin abrindo o diálogo de configurações."""
        # Criar o diálogo se for a primeira execução
        if self.dialog is None:
            self.dialog = DemToTactileDialog(self.iface, self.iface.mainWindow())
            
        # Mostrar o diálogo na tela
        self.dialog.show()
        # Trazer para frente se já estiver aberto
        self.dialog.raise_
        self.dialog.activateWindow()
        self.dialog.exec_()
