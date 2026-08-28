import os
import sys
import hashlib
import shutil
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import platform

# ==========================================
# 1. CONFIGURAÇÃO DE MODO
# ==========================================
MODO_REMOCAO = "QUARENTENA"

# ==========================================
# 2. BLINDAGEM DE SISTEMA E AMBIENTES DEV
# ==========================================
PASTAS_SISTEMA_PROIBIDAS = {
    "windows", "program files", "program files (x86)", "programdata",
    "system volume information", "$recycle.bin", "recovery", "appdata",
    "system", "library", "applications", "private", "cores", "volumes",
    ".spotlight-v100", ".fseventsd", ".trashes", ".trash",
    ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env", "__pycache__"
}

ARQUIVOS_SISTEMA_IGNORAR = {
    "thumbs.db", "desktop.ini", "pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr",
    ".ds_store", ".localized", ".icon\r"
}

TERMOS_BACKUP = ["backup", "bkp", "_old", "copia", "copias", "temp", "tmp", "antigo", "antigos"]

CATEGORIAS_EXTENSAO = {
    "Documentos_PDF": [".pdf"],
    "Documentos_Texto": [".doc", ".docx", ".odt", ".rtf", ".txt", ".md"],
    "Planilhas": [".xls", ".xlsx", ".ods", ".csv"],
    "Apresentacoes": [".ppt", ".pptx", ".odp"],
    "Imagens_Fotos": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v"],
    "Audio_Musica": [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"],
    "Arquivos_Compactados": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso"],
    "Codigos_e_Scripts": [".py", ".c", ".cpp", ".h", ".java", ".js", ".ts", ".html", ".css", ".json", ".sql", ".dart", ".swift", ".sh"],
    "Engenharia_CAD_3D": [".dwg", ".dxf", ".step", ".stp", ".iges", ".igs", ".stl", ".obj", ".sldprt", ".sldasm"]
}

# --- FUNÇÕES UTILITÁRIAS PARA ROLAGEM UNIVERSAL DO MOUSE ---
def bind_scroll(canvas):
    """Vincula o scroll do mouse ou trackpad universalmente ao canvas ativo."""
    def on_mousewheel(event):
        # Para Windows e macOS
        if platform.system() == 'Darwin': # Mac (Scroll invertido nativamente)
            canvas.yview_scroll(int(-1*(event.delta)), "units")
        else: # Windows
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            
    def on_mousewheel_linux_up(event):
        canvas.yview_scroll(-1, "units")
        
    def on_mousewheel_linux_down(event):
        canvas.yview_scroll(1, "units")

    # Associa os eventos apenas quando o mouse estiver em cima da janela
    def bound_to_mousewheel(event):
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_mousewheel_linux_up)
        canvas.bind_all("<Button-5>", on_mousewheel_linux_down)

    def unbound_to_mousewheel(event):
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind('<Enter>', bound_to_mousewheel)
    canvas.bind('<Leave>', unbound_to_mousewheel)

# --- LÓGICA DE DADOS ---
def eh_caminho_protegido(caminho):
    partes = [p.lower() for p in Path(caminho).resolve().parts]
    return any(protegida in partes for protegida in PASTAS_SISTEMA_PROIBIDAS)

def calcular_hash(caminho, bytes_parcial=None):
    hasher = hashlib.sha256()
    try:
        with open(caminho, "rb") as f:
            if bytes_parcial:
                hasher.update(f.read(bytes_parcial))
            else:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return None

def pontuar_caminho(caminho):
    caminho_lower = caminho.lower()
    eh_backup = any(termo in caminho_lower for termo in TERMOS_BACKUP)
    peso_backup = 1000 if eh_backup else 0
    profundidade = len(Path(caminho).resolve().parts)
    return (peso_backup, profundidade, os.path.getmtime(caminho))

def encontrar_destino_seguro(lista_caminhos, diretorio_raiz):
    caminhos_dir = [os.path.dirname(os.path.abspath(p)) for p in lista_caminhos]
    ancestral = os.path.commonpath(caminhos_dir)
    if os.path.abspath(ancestral) == os.path.abspath(diretorio_raiz):
        melhor_arquivo = min(lista_caminhos, key=pontuar_caminho)
        return os.path.dirname(os.path.abspath(melhor_arquivo))
    return ancestral

def formatar_tamanho(bytes_tam):
    for unidade in ['B', 'KB', 'MB', 'GB']:
        if bytes_tam < 1024.0:
            return f"{bytes_tam:.2f} {unidade}"
        bytes_tam /= 1024.0
    return f"{bytes_tam:.2f} TB"

def buscar_duplicatas(diretorio_alvo, pasta_quarentena):
    arquivos_por_tamanho = defaultdict(list)
    for raiz, subpastas, arquivos in os.walk(diretorio_alvo):
        subpastas[:] = [d for d in subpastas if d.lower() not in PASTAS_SISTEMA_PROIBIDAS and "_QUARENTENA" not in d]
        if eh_caminho_protegido(raiz) or (pasta_quarentena and pasta_quarentena in raiz):
            continue
        for nome in arquivos:
            if nome.lower() in ARQUIVOS_SISTEMA_IGNORAR or nome.startswith("._"):
                continue
            caminho = os.path.join(raiz, nome)
            try:
                tam = os.path.getsize(caminho)
                if tam > 0:
                    arquivos_por_tamanho[tam].append(caminho)
            except (OSError, PermissionError):
                continue

    potenciais = {tam: arqs for tam, arqs in arquivos_por_tamanho.items() if len(arqs) > 1}
    arquivos_por_hash = defaultdict(list)

    for _, lista_arqs in potenciais.items():
        parciais = defaultdict(list)
        for arq in lista_arqs:
            h_part = calcular_hash(arq, bytes_parcial=4096)
            if h_part:
                parciais[h_part].append(arq)

        for _, arqs_colidindo in parciais.items():
            if len(arqs_colidindo) > 1:
                for arq in arqs_colidindo:
                    h_full = calcular_hash(arq)
                    if h_full:
                        arquivos_por_hash[h_full].append(arq)

    grupos = {}
    for h, lista in arquivos_por_hash.items():
        if len(lista) > 1:
            mestre_sugerido = min(lista, key=pontuar_caminho)
            destino_ancestral = encontrar_destino_seguro(lista, diretorio_alvo)
            tamanho = os.path.getsize(mestre_sugerido)
            grupos[h] = {
                "arquivos": lista,
                "mestre_sugerido": mestre_sugerido,
                "ancestral": destino_ancestral,
                "tamanho": tamanho
            }
    return grupos

def listar_pastas_vazias(diretorio_raiz, pasta_quarentena):
    pastas_vazias = []
    for raiz, _, _ in os.walk(diretorio_raiz, topdown=False):
        if raiz == diretorio_raiz or (pasta_quarentena and pasta_quarentena in raiz) or eh_caminho_protegido(raiz):
            continue
        try:
            itens = os.listdir(raiz)
            itens_uteis = [item for item in itens if item.lower() not in ARQUIVOS_SISTEMA_IGNORAR and not item.startswith("._")]
            if not itens_uteis:
                pastas_vazias.append(raiz)
        except (PermissionError, OSError):
            continue
    return pastas_vazias

def listar_arquivos_para_categorizar(diretorio_raiz, pasta_quarentena, pasta_organizada):
    arquivos_por_tipo = defaultdict(list)
    for raiz, subpastas, arquivos in os.walk(diretorio_raiz):
        subpastas[:] = [d for d in subpastas if d.lower() not in PASTAS_SISTEMA_PROIBIDAS]
        if eh_caminho_protegido(raiz) or (pasta_quarentena and pasta_quarentena in raiz) or (pasta_organizada and pasta_organizada in raiz):
            continue
        for nome in arquivos:
            if nome.lower() in ARQUIVOS_SISTEMA_IGNORAR or nome.startswith("._"):
                continue
            caminho = os.path.join(raiz, nome)
            _, ext = os.path.splitext(nome)
            ext_l = ext.lower()
            categoria = "Outros"
            for cat, extensoes in CATEGORIAS_EXTENSAO.items():
                if ext_l in extensoes:
                    categoria = cat
                    break
            arquivos_por_tipo[categoria].append(caminho)
    return arquivos_por_tipo


# --- ETAPA 3: CATEGORIAS (OPCIONAL) ---
class JanelaOrganizacaoTipos(tk.Toplevel):
    def __init__(self, parent, diretorio_raiz, arquivos_por_tipo):
        super().__init__(parent)
        self.title("Etapa 3 de 3: Organizar Arquivos por Categoria (Opcional)")
        self.geometry("1180x800")
        self.configure(bg="#F0F2F5")
        self.diretorio_raiz = diretorio_raiz
        self.arquivos_por_tipo = arquivos_por_tipo
        self.pasta_destino_base = os.path.join(diretorio_raiz, "_ARQUIVOS_ORGANIZADOS")
        self.checkbox_vars = {}
        self.lbl_contador = None
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, bg="#FFFFFF", padx=24, pady=18, relief=tk.SOLID, bd=1)
        topo.pack(fill=tk.X)

        tk.Label(topo, text="ETAPA 3: REORGANIZAR ARQUIVOS POR TIPO (OPCIONAL)", font=("Helvetica", 17, "bold"), fg="#000000", bg="#FFFFFF").pack(anchor="w")
        tk.Label(topo, text="• Esta etapa é OPCIONAL. Todos os arquivos começam desmarcados por padrão.", font=("Helvetica", 13, "bold"), fg="#B3261E", bg="#FFFFFF").pack(anchor="w", pady=(4, 0))
        tk.Label(topo, text=f"• Destino: {self.pasta_destino_base}/[Nome_Da_Categoria]/", font=("Helvetica", 12), fg="#333333", bg="#FFFFFF").pack(anchor="w")

        painel_cont = tk.Frame(topo, bg="#E8F0FE", padx=14, pady=8, relief=tk.SOLID, bd=1)
        painel_cont.pack(fill=tk.X, pady=(10, 0))
        self.lbl_contador = tk.Label(painel_cont, text="Arquivos selecionados para mover: 0 (0.00 MB)", font=("Helvetica", 13, "bold"), fg="#000000", bg="#E8F0FE")
        self.lbl_contador.pack(anchor="w")

        container = tk.Frame(self, bg="#F0F2F5")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        canvas = tk.Canvas(container, bg="#F0F2F5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas, bg="#F0F2F5")

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        
        # Aplica a função de Scroll Universal
        bind_scroll(canvas)

        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        for categoria, arquivos in sorted(self.arquivos_por_tipo.items()):
            grupo_box = tk.LabelFrame(
                frame_conteudo, 
                text=f"  CATEGORIA: {categoria} ({len(arquivos)} arquivo(s))  ", 
                font=("Helvetica", 13, "bold"), fg="#000000", bg="#FFFFFF", padx=16, pady=12, relief=tk.SOLID, bd=1
            )
            grupo_box.pack(fill=tk.X, expand=True, padx=5, pady=8)

            for arq in arquivos:
                var = tk.BooleanVar(value=False)
                self.checkbox_vars[arq] = (var, categoria)
                tam_arq = os.path.getsize(arq) if os.path.exists(arq) else 0
                chk = tk.Checkbutton(
                    grupo_box, text=f"  Mover ({formatar_tamanho(tam_arq)}):  {arq}", 
                    variable=var, font=("Helvetica", 12), fg="#000000", bg="#FFFFFF", 
                    activebackground="#FFFFFF", anchor="w", justify=tk.LEFT,
                    command=self.atualizar_contador
                )
                chk.pack(fill=tk.X, anchor="w", pady=3)

        rodape = tk.Frame(self, bg="#FFFFFF", padx=24, pady=16, relief=tk.SOLID, bd=1)
        rodape.pack(fill=tk.X)

        btn_pular = tk.Button(
            rodape, text="  Finalizar sem Mover Nada  ", command=self.ao_fechar, 
            bg="#F1F3F4", fg="#000000", font=("Helvetica", 13, "bold"), padx=18, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_pular.pack(side=tk.LEFT)

        btn_mover = tk.Button(
            rodape, text="  Mover Arquivos Marcados para Pastas  ", command=self.executar_organizacao, 
            bg="#CEEAD6", fg="#000000", font=("Helvetica", 13, "bold"), padx=22, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_mover.pack(side=tk.RIGHT)

        self.atualizar_contador()

    def atualizar_contador(self):
        selecionados = 0
        total_bytes = 0
        for arq, (var, _) in self.checkbox_vars.items():
            if var.get():
                selecionados += 1
                if os.path.exists(arq):
                    total_bytes += os.path.getsize(arq)
        self.lbl_contador.config(text=f"Arquivos selecionados para mover: {selecionados} ({formatar_tamanho(total_bytes)})")

    def executar_organizacao(self):
        arquivos_para_mover = [(arq, cat) for arq, (var, cat) in self.checkbox_vars.items() if var.get()]
        if not arquivos_para_mover:
            messagebox.showinfo("Aviso", "Nenhum arquivo foi selecionado.", parent=self)
            return

        if not messagebox.askyesno("Confirmar", f"Mover {len(arquivos_para_mover)} arquivo(s) para pastas categorizadas?", parent=self):
            return

        movidos = 0
        for arq, cat in arquivos_para_mover:
            try:
                pasta_destino = os.path.join(self.pasta_destino_base, cat)
                os.makedirs(pasta_destino, exist_ok=True)
                nome_base = os.path.basename(arq)
                destino_final = os.path.join(pasta_destino, nome_base)
                c = 1
                while os.path.exists(destino_final):
                    n, ext = os.path.splitext(nome_base)
                    destino_final = os.path.join(pasta_destino, f"{n}_{c}{ext}")
                    c += 1
                shutil.move(arq, destino_final)
                movidos += 1
            except Exception as e:
                print(f"Erro ao mover {arq}: {e}")

        messagebox.showinfo("Sucesso", f"Organização concluída!\nArquivos movidos: {movidos}", parent=self)
        self.ao_fechar()

    def ao_fechar(self):
        self.master.destroy()

# --- ETAPA 2: PASTAS VAZIAS ---
class JanelaPastasVazias(tk.Toplevel):
    def __init__(self, parent, diretorio_raiz, pastas_vazias, pasta_quarentena):
        super().__init__(parent)
        self.title("Etapa 2 de 3: Eliminação de Pastas Vazias")
        self.geometry("1180x800")
        self.configure(bg="#F0F2F5")
        self.diretorio_raiz = diretorio_raiz
        self.pastas_vazias = pastas_vazias
        self.pasta_quarentena = pasta_quarentena
        self.checkbox_vars = {}
        self.lbl_contador = None
        self.protocol("WM_DELETE_WINDOW", self.avancar_para_etapa3)
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, bg="#FFFFFF", padx=24, pady=18, relief=tk.SOLID, bd=1)
        topo.pack(fill=tk.X)

        tk.Label(topo, text="ETAPA 2: ELIMINAÇÃO DE PASTAS VAZIAS", font=("Helvetica", 17, "bold"), fg="#000000", bg="#FFFFFF").pack(anchor="w")
        tk.Label(topo, text=f"• Diretório: {self.diretorio_raiz}", font=("Helvetica", 12), fg="#333333", bg="#FFFFFF").pack(anchor="w", pady=(2, 0))
        tk.Label(topo, text="• REGRAS: [Marcado] = Pasta será apagada  |  [Desmarcado] = Pasta será preservada.", font=("Helvetica", 13, "bold"), fg="#B3261E", bg="#FFFFFF").pack(anchor="w", pady=(4, 0))

        painel_cont = tk.Frame(topo, bg="#FCE8E6", padx=14, pady=8, relief=tk.SOLID, bd=1)
        painel_cont.pack(fill=tk.X, pady=(10, 0))
        self.lbl_contador = tk.Label(painel_cont, text="", font=("Helvetica", 13, "bold"), fg="#000000", bg="#FCE8E6")
        self.lbl_contador.pack(anchor="w")

        container = tk.Frame(self, bg="#F0F2F5")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        canvas = tk.Canvas(container, bg="#F0F2F5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas, bg="#F0F2F5")

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        
        # Aplica a função de Scroll Universal
        bind_scroll(canvas)

        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        caixa_pastas = tk.LabelFrame(
            frame_conteudo, text=" SELECIONE AS PASTAS VAZIAS PARA EXCLUIR: ", 
            font=("Helvetica", 13, "bold"), fg="#000000", bg="#FFFFFF", padx=16, pady=12, relief=tk.SOLID, bd=1
        )
        caixa_pastas.pack(fill=tk.X, expand=True, padx=5, pady=5)

        for pasta in self.pastas_vazias:
            var = tk.BooleanVar(value=True)
            self.checkbox_vars[pasta] = var
            chk = tk.Checkbutton(
                caixa_pastas, text=f"  Excluir pasta vazia:  {pasta}", variable=var, 
                font=("Helvetica", 12), fg="#B3261E", bg="#FFFFFF", activebackground="#FFFFFF", 
                anchor="w", justify=tk.LEFT,
                command=self.atualizar_contador
            )
            chk.pack(fill=tk.X, anchor="w", pady=3)

        rodape = tk.Frame(self, bg="#FFFFFF", padx=24, pady=16, relief=tk.SOLID, bd=1)
        rodape.pack(fill=tk.X)

        btn_pular = tk.Button(
            rodape, text="  Pular Pastas Vazias ->  ", command=self.avancar_para_etapa3, 
            bg="#F1F3F4", fg="#000000", font=("Helvetica", 13, "bold"), padx=18, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_pular.pack(side=tk.LEFT)

        btn_excluir = tk.Button(
            rodape, text="  Excluir Pastas Marcadas e Avançar ->  ", command=self.executar_exclusao, 
            bg="#FCE8E6", fg="#000000", font=("Helvetica", 13, "bold"), padx=22, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_excluir.pack(side=tk.RIGHT)

        self.atualizar_contador()

    def atualizar_contador(self):
        selecionadas = sum(1 for v in self.checkbox_vars.values() if v.get())
        total = len(self.checkbox_vars)
        self.lbl_contador.config(text=f"Pastas vazias selecionadas para exclusão: {selecionadas} de {total}")

    def executar_exclusao(self):
        pastas_para_remover = [p for p, v in self.checkbox_vars.items() if v.get()]
        if pastas_para_remover:
            if messagebox.askyesno("Confirmar", f"Excluir permanentemente {len(pastas_para_remover)} pasta(s) vazia(s)?", parent=self):
                pastas_para_remover.sort(key=len, reverse=True)
                for pasta in pastas_para_remover:
                    try:
                        for item in os.listdir(pasta):
                            if item.lower() in ARQUIVOS_SISTEMA_IGNORAR or item.startswith("._"):
                                os.remove(os.path.join(pasta, item))
                        os.rmdir(pasta)
                    except Exception as e:
                        print(f"Erro ao remover {pasta}: {e}")
        self.avancar_para_etapa3()

    def avancar_para_etapa3(self):
        self.withdraw()
        pasta_organizada = os.path.join(self.diretorio_raiz, "_ARQUIVOS_ORGANIZADOS")
        arquivos_tipo = listar_arquivos_para_categorizar(self.diretorio_raiz, self.pasta_quarentena, pasta_organizada)
        if arquivos_tipo:
            JanelaOrganizacaoTipos(self.master, self.diretorio_raiz, arquivos_tipo)
        else:
            messagebox.showinfo("Concluído", "Processo finalizado com sucesso!")
            self.master.destroy()

# --- ETAPA 1: DUPLICATAS (COM CALCULADORA DE ESPAÇO) ---
class JanelaPrincipal(tk.Tk):
    def __init__(self, diretorio_origem, grupos):
        super().__init__()
        self.title("Etapa 1 de 3: Deduplicação e Consolidação de Espaço")
        self.geometry("1200x820")
        self.configure(bg="#F0F2F5")
        
        self.diretorio_origem = diretorio_origem
        self.grupos = grupos
        self.pasta_quarentena = os.path.join(diretorio_origem, "_QUARENTENA_DUPLICATAS")
        
        self.mestre_selecionado = {} 
        self.duplicatas_vars = {}    
        self.lbl_contador_topo = None
        
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, bg="#FFFFFF", padx=24, pady=18, relief=tk.SOLID, bd=1)
        topo.pack(fill=tk.X)

        tk.Label(topo, text="ETAPA 1: REVISÃO MANUAL DE ARQUIVOS DUPLICADOS", font=("Helvetica", 17, "bold"), fg="#000000", bg="#FFFFFF").pack(anchor="w")
        tk.Label(topo, text=f"• Disco/Pasta: {self.diretorio_origem}  |  Modo: [{MODO_REMOCAO}]", font=("Helvetica", 12), fg="#333333", bg="#FFFFFF").pack(anchor="w", pady=(2, 0))
        
        painel_regras = tk.Frame(topo, bg="#FFF8E1", padx=12, pady=6, relief=tk.SOLID, bd=1)
        painel_regras.pack(fill=tk.X, pady=(6, 6))
        tk.Label(
            painel_regras, 
            text="COMO FUNCIONA ESTA TELA:\n"
                 "1. [VERDE]: Escolha o arquivo que ficará intacto no disco.\n"
                 "2. [VERMELHO MARCADO]: O arquivo SERÁ RETIRADO e enviado para a Quarentena/Exclusão.\n"
                 "3. [VERMELHO DESMARCADO]: O arquivo NÃO SERÁ TOCADO (fica no local original).",
            font=("Helvetica", 12, "bold"), fg="#000000", bg="#FFF8E1", justify=tk.LEFT
        ).pack(anchor="w")

        painel_calc = tk.Frame(topo, bg="#D2E3FC", padx=14, pady=8, relief=tk.SOLID, bd=1)
        painel_calc.pack(fill=tk.X)
        self.lbl_contador_topo = tk.Label(
            painel_calc, text="", font=("Helvetica", 14, "bold"), fg="#000000", bg="#D2E3FC"
        )
        self.lbl_contador_topo.pack(anchor="w")

        container = tk.Frame(self, bg="#F0F2F5")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        canvas = tk.Canvas(container, bg="#F0F2F5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas, bg="#F0F2F5")

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        
        # Aplica a função de Scroll Universal
        bind_scroll(canvas)

        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        for idx, (h, dados) in enumerate(self.grupos.items(), start=1):
            lista_arqs = dados["arquivos"]
            mestre_padrao = dados["mestre_sugerido"]
            tam_formatado = formatar_tamanho(dados["tamanho"])

            grupo_box = tk.LabelFrame(
                frame_conteudo, 
                text=f" GRUPO {idx}  |  Tamanho Unitário: {tam_formatado}  |  SHA-256: {h[:12]}... ", 
                font=("Helvetica", 13, "bold"), fg="#000000", bg="#FFFFFF", padx=16, pady=12, relief=tk.SOLID, bd=1
            )
            grupo_box.pack(fill=tk.X, expand=True, padx=5, pady=10)

            var_mestre = tk.StringVar(value=mestre_padrao)
            self.mestre_selecionado[h] = var_mestre

            frame_mestre = tk.Frame(grupo_box, bg="#CEEAD6", padx=14, pady=10, relief=tk.SOLID, bd=1)
            frame_mestre.pack(fill=tk.X, pady=(0, 8))
            
            tk.Label(
                frame_mestre, text="✓ ESCOLHA O ARQUIVO QUE SERÁ PRESERVADO:", 
                font=("Helvetica", 12, "bold"), fg="#000000", bg="#CEEAD6"
            ).pack(anchor="w", pady=(0, 4))

            for arq in lista_arqs:
                eh_bkp = any(t in arq.lower() for t in TERMOS_BACKUP)
                tag_bkp = " [PASTA DE BACKUP]" if eh_bkp else " [PASTA PRINCIPAL]"
                
                rb = tk.Radiobutton(
                    frame_mestre, text=f"  Manter este:  {arq}{tag_bkp}", 
                    variable=var_mestre, value=arq, font=("Helvetica", 12), 
                    fg="#000000", bg="#CEEAD6", activebackground="#CEEAD6", 
                    anchor="w", justify=tk.LEFT,
                    command=lambda h_ref=h: self.ao_mudar_mestre(h_ref)
                )
                rb.pack(fill=tk.X, anchor="w", pady=2)

            frame_dups = tk.Frame(grupo_box, bg="#FCE8E6", padx=14, pady=10, relief=tk.SOLID, bd=1)
            frame_dups.pack(fill=tk.X)

            acao_label = "QUARENTENA" if MODO_REMOCAO == "QUARENTENA" else ("LIXEIRA" if MODO_REMOCAO == "LIXEIRA" else "EXCLUSÃO")
            tk.Label(
                frame_dups, 
                text=f"✗ SELEÇÃO DE DUPLICATAS (Marcado = Enviar para {acao_label} | Desmarcado = Não Tocar):", 
                font=("Helvetica", 12, "bold"), fg="#000000", bg="#FCE8E6"
            ).pack(anchor="w", pady=(0, 4))

            for arq in lista_arqs:
                var_dup = tk.BooleanVar(value=(arq != mestre_padrao))
                self.duplicatas_vars[arq] = (var_dup, h)
                
                chk = tk.Checkbutton(
                    frame_dups, text=f"  Enviar para {acao_label}:  {arq}", 
                    variable=var_dup, font=("Helvetica", 12), 
                    fg="#000000", bg="#FCE8E6", activebackground="#FCE8E6", 
                    anchor="w", justify=tk.LEFT,
                    command=self.calcular_espaco_liberado
                )
                chk.pack(fill=tk.X, anchor="w", pady=2)

        rodape = tk.Frame(self, bg="#FFFFFF", padx=24, pady=16, relief=tk.SOLID, bd=1)
        rodape.pack(fill=tk.X)

        btn_cancelar = tk.Button(
            rodape, text="  Cancelar Tudo  ", command=self.destroy, 
            bg="#F1F3F4", fg="#000000", font=("Helvetica", 13, "bold"), padx=18, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_cancelar.pack(side=tk.LEFT)

        btn_processar = tk.Button(
            rodape, text="  Aplicar Seleção e Avançar para Pastas Vazias ->  ", command=self.executar_processamento, 
            bg="#D2E3FC", fg="#000000", font=("Helvetica", 13, "bold"), padx=22, pady=10, relief=tk.SOLID, bd=1, cursor="hand2"
        )
        btn_processar.pack(side=tk.RIGHT)

        self.calcular_espaco_liberado()

    def ao_mudar_mestre(self, h):
        mestre_atual = self.mestre_selecionado[h].get()
        for arq in self.grupos[h]["arquivos"]:
            if arq in self.duplicatas_vars:
                var, _ = self.duplicatas_vars[arq]
                var.set(arq != mestre_atual)
        self.calcular_espaco_liberado()

    def calcular_espaco_liberado(self):
        total_arquivos_marcados = 0
        total_bytes = 0
        
        for arq, (var, h) in self.duplicatas_vars.items():
            if var.get():
                total_arquivos_marcados += 1
                tamanho = self.grupos[h]["tamanho"]
                total_bytes += tamanho

        texto = f"Total de arquivos duplicados marcados para remoção: {total_arquivos_marcados}  |  Espaço a ser liberado: {formatar_tamanho(total_bytes)}"
        self.lbl_contador_topo.config(text=texto)

    def executar_processamento(self):
        arquivos_para_mover = [arq for arq, (var, _) in self.duplicatas_vars.items() if var.get()]
        
        msg = f"Deseja processar {len(arquivos_para_mover)} arquivo(s) duplicado(s) usando o modo [{MODO_REMOCAO}]?"
        if not messagebox.askyesno("Confirmar Execução", msg, parent=self):
            return

        if MODO_REMOCAO == "QUARENTENA":
            os.makedirs(self.pasta_quarentena, exist_ok=True)

        for h, dados in self.grupos.items():
            mestre = self.mestre_selecionado[h].get()
            ancestral = dados["ancestral"]
            caminho_ideal = os.path.join(ancestral, os.path.basename(mestre))
            
            if os.path.abspath(mestre) != os.path.abspath(caminho_ideal) and os.path.exists(mestre):
                if not os.path.exists(caminho_ideal):
                    try:
                        shutil.move(mestre, caminho_ideal)
                    except Exception as e:
                        print(f"Erro ao mover mestre {mestre}: {e}")

        for arq in arquivos_para_mover:
            if os.path.exists(arq):
                try:
                    if MODO_REMOCAO == "EXCLUIR":
                        os.remove(arq)
                    elif MODO_REMOCAO == "LIXEIRA":
                        try:
                            import send2trash
                            send2trash.send2trash(arq)
                        except ImportError:
                            os.makedirs(self.pasta_quarentena, exist_ok=True)
                            shutil.move(arq, os.path.join(self.pasta_quarentena, os.path.basename(arq)))
                    else:
                        nome_base = os.path.basename(arq)
                        destino = os.path.join(self.pasta_quarentena, nome_base)
                        c = 1
                        while os.path.exists(destino):
                            n, ext = os.path.splitext(nome_base)
                            destino = os.path.join(self.pasta_quarentena, f"{n}_{c}{ext}")
                            c += 1
                        shutil.move(arq, destino)
                except Exception as e:
                    print(f"Erro ao processar {arq}: {e}")

        self.withdraw()
        pastas_vazias = listar_pastas_vazias(self.diretorio_origem, self.pasta_quarentena)
        if pastas_vazias:
            JanelaPastasVazias(self, self.diretorio_origem, pastas_vazias, self.pasta_quarentena)
        else:
            pasta_organizada = os.path.join(self.diretorio_origem, "_ARQUIVOS_ORGANIZADOS")
            arquivos_tipo = listar_arquivos_para_categorizar(self.diretorio_origem, self.pasta_quarentena, pasta_organizada)
            if arquivos_tipo:
                JanelaOrganizacaoTipos(self, self.diretorio_origem, arquivos_tipo)
            else:
                messagebox.showinfo("Finalizado", "Disco limpo e organizado com segurança!")
                self.destroy()

def iniciar():
    root = tk.Tk()
    root.withdraw()

    messagebox.showinfo("Organizador Seguro", "Selecione o HD ou SSD para iniciar o processo.")
    diretorio = filedialog.askdirectory(title="Selecione o Disco")
    
    if not diretorio:
        return

    if os.path.abspath(diretorio) in ["/", "C:\\"]:
        if not messagebox.askyesno("Alerta de Segurança", "Você selecionou a unidade raiz principal do sistema. As pastas de sistema serão ignoradas. Deseja continuar?"):
            return

    pasta_quarentena = os.path.join(diretorio, "_QUARENTENA_DUPLICATAS")
    pasta_organizada = os.path.join(diretorio, "_ARQUIVOS_ORGANIZADOS")
    
    print(f"[*] Varrendo disco: {diretorio}...")
    grupos = buscar_duplicatas(diretorio, pasta_quarentena)

    if grupos:
        app = JanelaPrincipal(diretorio, grupos)
        app.mainloop()
    else:
        pastas_vazias = listar_pastas_vazias(diretorio, pasta_quarentena)
        if pastas_vazias:
            JanelaPastasVazias(root, diretorio, pastas_vazias, pasta_quarentena)
            root.mainloop()
        else:
            arquivos_tipo = listar_arquivos_para_categorizar(diretorio, pasta_quarentena, pasta_organizada)
            if arquivos_tipo:
                JanelaOrganizacaoTipos(root, diretorio, arquivos_tipo)
                root.mainloop()
            else:
                messagebox.showinfo("Resultado", "O disco selecionado já está totalmente limpo e estruturado!")

if __name__ == "__main__":
    iniciar()