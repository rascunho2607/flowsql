"""
FlowSQL — Entry point
Run: python main.py
"""
import sys
import os

# Ensure the flowsql package root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from themes.theme_manager import ThemeManager
from app.main_window import MainWindow


def main():
    # Enable high-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("FlowSQL")
    app.setOrganizationName("FlowSQL")

    theme_manager = ThemeManager(app)
    theme_manager.apply_theme("dark")  # Dark mode by default

    window = MainWindow(app, theme_manager)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


# 1- alista de objetos ter uma aba com os bancos acessados recentes, independente do servidor. E uma terceira aba com os bancos favoritos do usuário. organizados
#  separados por servidor.

# 2- a opção de ao clicar com o direito em um banco, ter a opção de "abrir nova aba com esse banco" ou "definir como favorito". E na aba de favoritos, clicar com o
#  direito em um banco para "remover dos favoritos".

# 3- uma nova funcionalidade é definir o banco no projeto com um click o app ir até p app.setting do SOFC e configurar o acesso ao cliente.

# 4- seria interessante se para o node join cada card de comparação tivesse um contexto assim um único join seria necesário para um consulta complexa e para n fazerem 
# vários joni com a mesma tabela ele gerenciasse para por na mesma linha o novo join caso a tabela se repetisso exemplo li.idItem = i.idItem e em outro card 
# i.idItem = lci.IdItem ele colocasse os dois na mesma linha do join e apena se uma nova conexão de i.item vinda de outra dataset tbItem fosse feita seria criado um 
# novo join para ele. a ideia é cada dataset seria um join e cada comparação entre colunas de datasets diferentes seria uma linha do join. E se a comparação for entre 
# colunas do mesmo dataset, ela seria colocada na mesma linha do join. Assim, o usuário poderia criar consultas complexas com poucos joins e sem repetir tabelas 
# desnecessariamente.

# melhorar o UX das conexões mudando o tipo do cursor quando estiver sobre um ponto de conexão saida e ao segurar o ponto para conectar o ponto q será conectado
# destacar com uma borda ou algo do tipo.
# E no node select por barras de rolagem horizontal e vertical para poder ver mais do resultado e mudar o cursor ao passar sobre os ponto de redimecionamento do node.