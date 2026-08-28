import os
import sys
import hashlib
import shutil
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ==========================================
# 1. CONFIGURAÇÃO DO MODO DE REMOÇÃO
# ==========================================
# "QUARENTENA" -> Move para a pasta _QUARENTENA_DUPLICATAS (Mais Seguro)
# "LIXEIRA"    -> Envia para a Lixeira nativa (requer: pip install send2trash)
# "EXCLUIR"    -> Apaga definitivamente do disco (os.remove)
MODO_REMOCAO = "QUARENTENA"

# ==========================================
# 2. BLINDAGEM DE SISTEMA E AMBIENTES DEV
# ==========================================
# Pastas que o script NUNCA vai escanear, mover ou apagar
PASTAS_SISTEMA_PROIBIDAS = {
    # Windows
    "windows", "program files", "program files (x86)", "programdata",
    "system volume information", "$recycle.bin", "recovery", "appdata",
    # macOS
    "system", "library", "applications", "private", "cores", "volumes",
    ".spotlight-v100", ".fseventsd", ".trashes", ".trash",
    # Dev & Ambientes (Evita quebrar projetos e pacotes)
    ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env", "__pycache__"
}

# Arquivos de sistema para NUNCA analisar nem mover
ARQUIVOS_SISTEMA_IGNORAR = {
    # Windows
    "thumbs.db", "desktop.ini", "pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr",
    # macOS
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

def eh_caminho_protegido(caminho):
    """Verifica se o caminho passa por alguma pasta restrita de sistema."""
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

def buscar_duplicatas(diretorio_alvo, pasta_quarentena):
    arquivos_por_tamanho = defaultdict(list)
    
    for raiz, subpastas, arquivos in os.walk(diretorio_alvo):
        # 1. Poda diretórios proibidos em tempo real de varredura
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

    planos = {}
    for h, lista in arquivos_por_hash.items():
        if len(lista) > 1:
            mestre = min(lista, key=pontuar_caminho)
            duplicatas = [f for f in lista if f != mestre]
            
            destino_ancestral = encontrar_destino_seguro(lista, diretorio_alvo)
            nome_arq = os.path.basename(mestre)
            caminho_ideal = os.path.join(destino_ancestral, nome_arq)
            promover_para = None if os.path.abspath(mestre) == os.path.abspath(caminho_ideal) else caminho_ideal

            planos[h] = {
                "ancestral": destino_ancestral,
                "mestre": mestre,
                "promover_para": promover_para,
                "duplicatas": duplicatas
            }
    return planos

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
        self.title("Etapa 3 de 3: Reorganizar por Categoria (Opcional)")
        self.geometry("980x680")
        self.diretorio_raiz = diretorio_raiz
        self.arquivos_por_tipo = arquivos_por_tipo
        self.pasta_destino_base = os.path.join(diretorio_raiz, "_ARQUIVOS_ORGANIZADOS")
        self.checkbox_vars = {}
        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, pady=10, padx=10)
        topo.pack(fill=tk.X)
        
        lbl_info = tk.Label(
            topo, 
            text=f"Diretório: {self.diretorio_raiz}\n"
                 f"Destino: {self.pasta_destino_base}/[Categoria]/\n"
                 f"Selecione apenas o que deseja categorizar (ou clique em 'Concluir' para encerrar):",
            justify=tk.LEFT, font=("Arial", 10)
        )
        lbl_info.pack(anchor="w")

        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas)

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        for categoria, arquivos in sorted(self.arquivos_por_tipo.items()):
            grupo_box = tk.LabelFrame(
                frame_conteudo, 
                text=f" {categoria} ({len(arquivos)} arquivo(s)) ", 
                font=("Arial", 9, "bold"), padx=8, pady=6
            )
            grupo_box.pack(fill=tk.X, expand=True, padx=5, pady=6)

            for arq in arquivos:
                var = tk.BooleanVar(value=False)
                self.checkbox_vars[arq] = (var, categoria)
                chk = tk.Checkbutton(
                    grupo_box, text=arq, variable=var, 
                    fg="#2c3e50", font=("Arial", 9), anchor="w", justify=tk.LEFT
                )
                chk.pack(fill=tk.X, anchor="w")

        rodape = tk.Frame(self, pady=10, padx=10)
        rodape.pack(fill=tk.X)
        btn_pular = tk.Button(rodape, text="Concluir / Não Mover Nada", command=self.ao_fechar, width=22)
        btn_pular.pack(side=tk.LEFT, padx=5)

        btn_mover = tk.Button(
            rodape, text="Mover Marcados para Pastas por Categoria", 
            command=self.executar_organizacao, bg="#27ae60", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4
        )
        btn_mover.pack(side=tk.RIGHT, padx=5)

    def executar_organizacao(self):
        arquivos_para_mover = [(arq, cat) for arq, (var, cat) in self.checkbox_vars.items() if var.get()]
        if not arquivos_para_mover:
            messagebox.showinfo("Aviso", "Nenhum arquivo selecionado.", parent=self)
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

        messagebox.showinfo("Finalizado", f"Organização concluída! Arquivos movidos: {movidos}", parent=self)
        self.ao_fechar()

    def ao_fechar(self):
        self.master.destroy()

# --- ETAPA 2: PASTAS VAZIAS ---
class JanelaPastasVazias(tk.Toplevel):
    def __init__(self, parent, diretorio_raiz, pastas_vazias, pasta_quarentena):
        super().__init__(parent)
        self.title("Etapa 2 de 3: Eliminar Pastas Vazias")
        self.geometry("900x600")
        self.diretorio_raiz = diretorio_raiz
        self.pastas_vazias = pastas_vazias
        self.pasta_quarentena = pasta_quarentena
        self.checkbox_vars = {}
        self.protocol("WM_DELETE_WINDOW", self.avancar_para_etapa3)
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, pady=10, padx=10)
        topo.pack(fill=tk.X)
        
        lbl_info = tk.Label(
            topo, 
            text=f"Diretório: {self.diretorio_raiz}\n"
                 f"Pastas vazias encontradas: {len(self.pastas_vazias)}\n"
                 f"Desmarque as pastas que NÃO deseja excluir:",
            justify=tk.LEFT, font=("Arial", 10)
        )
        lbl_info.pack(anchor="w")

        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas)

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        for pasta in self.pastas_vazias:
            var = tk.BooleanVar(value=True)
            self.checkbox_vars[pasta] = var
            chk = tk.Checkbutton(
                frame_conteudo, text=pasta, variable=var, 
                fg="#c0392b", font=("Arial", 9), anchor="w", justify=tk.LEFT
            )
            chk.pack(fill=tk.X, anchor="w", padx=5, pady=2)

        rodape = tk.Frame(self, pady=10, padx=10)
        rodape.pack(fill=tk.X)
        btn_pular = tk.Button(rodape, text="Pular Pastas Vazias ->", command=self.avancar_para_etapa3, width=18)
        btn_pular.pack(side=tk.LEFT, padx=5)

        btn_excluir = tk.Button(
            rodape, text="Excluir Selecionadas e Avançar ->", 
            command=self.executar_exclusao, bg="#c0392b", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4
        )
        btn_excluir.pack(side=tk.RIGHT, padx=5)

    def executar_exclusao(self):
        pastas_para_remover = [p for p, v in self.checkbox_vars.items() if v.get()]
        if pastas_para_remover:
            if messagebox.askyesno("Confirmar", f"Excluir {len(pastas_para_remover)} pasta(s) vazia(s)?", parent=self):
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

# --- ETAPA 1: DUPLICATAS ---
class JanelaPrincipal(tk.Tk):
    def __init__(self, diretorio_origem, planos):
        super().__init__()
        self.title("Etapa 1 de 3: Deduplicação e Consolidação Blindada")
        self.geometry("980x680")
        self.diretorio_origem = diretorio_origem
        self.planos = planos
        self.pasta_quarentena = os.path.join(diretorio_origem, "_QUARENTENA_DUPLICATAS")
        self.checkbox_vars = {}
        self.construir_interface()

    def construir_interface(self):
        topo = tk.Frame(self, pady=10, padx=10)
        topo.pack(fill=tk.X)
        
        lbl_info = tk.Label(
            topo, 
            text=f"Diretório: {self.diretorio_origem}\n"
                 f"Modo de Ação: [{MODO_REMOCAO}] | Pastas de sistema e de desenvolvimento protegidas.\n"
                 f"Pastas de 'backup' descartadas preferencialmente para manter as versões das pastas de trabalho.",
            justify=tk.LEFT, font=("Arial", 10)
        )
        lbl_info.pack(anchor="w")

        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frame_conteudo = tk.Frame(canvas)

        frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set, yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill=tk.Y)

        for idx, (h, plano) in enumerate(self.planos.items(), start=1):
            grupo_box = tk.LabelFrame(
                frame_conteudo, 
                text=f" Grupo {idx} | Destino Seguro: {plano['ancestral']} ", 
                font=("Arial", 9, "bold"), padx=8, pady=6
            )
            grupo_box.pack(fill=tk.X, expand=True, padx=5, pady=6)

            mestre = plano["mestre"]
            promover = plano["promover_para"]
            
            if promover:
                txt_mestre = f"[PROMOVER PARA PASTA SUPERIOR] \nDe: {mestre}\nPara: {promover}"
                cor_mestre = "#0055aa"
            else:
                txt_mestre = f"[PRESERVADO NA PASTA ATIVA] {mestre}"
                cor_mestre = "#007700"

            lbl_mestre = tk.Label(grupo_box, text=txt_mestre, fg=cor_mestre, font=("Arial", 9, "bold"), anchor="w", justify=tk.LEFT)
            lbl_mestre.pack(fill=tk.X, anchor="w", pady=2)

            for dup in plano["duplicatas"]:
                var = tk.BooleanVar(value=True)
                self.checkbox_vars[dup] = var
                eh_bkp = any(t in dup.lower() for t in TERMOS_BACKUP)
                tag_bkp = " [CÓPIA DE BACKUP]" if eh_bkp else ""
                
                acao_txt = "Quarentena" if MODO_REMOCAO == "QUARENTENA" else ("Lixeira" if MODO_REMOCAO == "LIXEIRA" else "Excluir")
                
                chk = tk.Checkbutton(
                    grupo_box, text=f"{acao_txt}{tag_bkp}: {dup}", 
                    variable=var, fg="#B22222", font=("Arial", 9), anchor="w", justify=tk.LEFT
                )
                chk.pack(fill=tk.X, anchor="w")

        rodape = tk.Frame(self, pady=10, padx=10)
        rodape.pack(fill=tk.X)

        btn_cancelar = tk.Button(rodape, text="Cancelar Tudo", command=self.destroy, width=12)
        btn_cancelar.pack(side=tk.LEFT, padx=5)

        btn_processar = tk.Button(
            rodape, text="Aplicar e Avançar para Pastas Vazias ->", 
            command=self.executar_processamento, bg="#0066cc", fg="white", font=("Arial", 10, "bold"), padx=10, pady=4
        )
        btn_processar.pack(side=tk.RIGHT, padx=5)

    def executar_processamento(self):
        if not messagebox.askyesno("Confirmar", f"Executar deduplicação usando o modo [{MODO_REMOCAO}]?", parent=self):
            return

        if MODO_REMOCAO == "QUARENTENA":
            os.makedirs(self.pasta_quarentena, exist_ok=True)
        
        for h, plano in self.planos.items():
            promover_para = plano["promover_para"]
            mestre = plano["mestre"]
            if promover_para and os.path.exists(mestre) and not os.path.exists(promover_para):
                try:
                    shutil.move(mestre, promover_para)
                except Exception as e:
                    print(f"Erro ao promover {mestre}: {e}")

        for arq, var in self.checkbox_vars.items():
            if var.get() and os.path.exists(arq):
                try:
                    if MODO_REMOCAO == "EXCLUIR":
                        os.remove(arq)
                    elif MODO_REMOCAO == "LIXEIRA":
                        try:
                            import send2trash
                            send2trash.send2trash(arq)
                        except ImportError:
                            # Fallback para quarentena caso falte a lib
                            os.makedirs(self.pasta_quarentena, exist_ok=True)
                            shutil.move(arq, os.path.join(self.pasta_quarentena, os.path.basename(arq)))
                    else: # QUARENTENA
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

    messagebox.showinfo("Organizador Seguro Multiplataforma", "Selecione o HD ou SSD para iniciar o processo.")
    diretorio = filedialog.askdirectory(title="Selecione a Unidade ou Pasta")
    
    if not diretorio:
        return

    # Trava adicional para caso o usuário selecione acidentalmente a raiz de boot do sistema no Mac/Linux
    if os.path.abspath(diretorio) in ["/", "C:\\"]:
        if not messagebox.askyesno("Alerta de Segurança", "Você selecionou a unidade raiz principal do sistema. As pastas de sistema serão ignoradas por segurança. Deseja prosseguir?"):
            return

    pasta_quarentena = os.path.join(diretorio, "_QUARENTENA_DUPLICATAS")
    pasta_organizada = os.path.join(diretorio, "_ARQUIVOS_ORGANIZADOS")
    
    planos = buscar_duplicatas(diretorio, pasta_quarentena)

    if planos:
        app = JanelaPrincipal(diretorio, planos)
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