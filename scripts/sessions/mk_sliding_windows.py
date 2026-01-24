import json
import os
import sys

# ================= CONFIGURAZIONE =================
# INPUT_FILE e OUTPUT_FILE verranno definiti nel main
INPUT_FILE = None
OUTPUT_FILE = None

# Dimensione della finestra di predizione (quanti comandi futuri prevedere)
WINDOW_SIZE = 6 

# Separatore utilizzato per concatenare i comandi nella stringa (es. "cmd1 ; cmd2")
CMD_SEPARATOR = " ; "

# LISTA DI ESCLUSIONE OUTPUT
# I comandi inseriti qui verranno rimossi SOLO dalla parte "output".

# 2. ESCLUSIONE PER MATCH ESATTO (Blacklist puntuale)
# Comandi specifici da rimuovere se non catturati dai prefissi
OUTPUT_BLOCKLIST_EXACT = {
    "exit", "logout", "quit", "bye",
    "clear", "reset", "cls",
    "true", "false", ":",
    "w", "id", "whoami", "pwd",
    "enable", "system", "shell", "sh", "/bin/sh", "/bin/busybox",
    "linuxshell", "bash"
}

def process_sliding_window():
    # Verifica che INPUT_FILE sia stato impostato correttamente
    if not INPUT_FILE or not OUTPUT_FILE:
        print("[!] Errore: File di input o output non definiti.")
        return

    print(f"[*] Inizio elaborazione da: {INPUT_FILE}")
    
    training_data = []
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            # Carichiamo il file. Si presume sia un JSON Array valido
            try:
                sessions = json.load(f)
            except json.JSONDecodeError:
                # Fallback se il file fosse in formato NDJSON
                f.seek(0)
                sessions = [json.loads(line) for line in f if line.strip()]

        print(f"[*] Sessioni caricate: {len(sessions)}")
        
        count_examples = 0

        for session in sessions:
            # Recuperiamo la lista dei comandi dalla sessione
            commands = session.get('commands', [])
            
            # Se la sessione ha meno di 2 comandi, non c'è nulla da predire
            if len(commands) < 2:
                continue

           # --- LOGICA SLIDING WINDOW ---
            for i in range(1, len(commands)):
                
                # 1. Definizione INPUT (Mantiene TUTTO per il contesto)
                input_seq_list = commands[:i]
                
                # 2. Definizione OUTPUT GREZZO
                raw_output_list = commands[i : i + WINDOW_SIZE]
                
                # 3. FILTRO OUTPUT AVANZATO
                filtered_output_list = []
                for cmd in raw_output_list:
                    cmd_clean = cmd.strip()
                    
                    # B. Controllo Esatto (es. "exit")
                    if cmd_clean in OUTPUT_BLOCKLIST_EXACT:
                        continue
                        
                    # Se passa entrambi i controlli, lo teniamo
                    filtered_output_list.append(cmd_clean)
                
                # Se l'output è vuoto dopo il filtro, saltiamo questo esempio
                if not filtered_output_list:
                    continue

                # 4. Creazione stringhe
                input_string = CMD_SEPARATOR.join(input_seq_list)
                output_string = CMD_SEPARATOR.join(filtered_output_list)

                # 5. Aggiunta al dataset
                example = {
                    #"prompt": "Role: Predictive Honeypot. Analyze SSH session. Predict the next high-value commands (downloads, execution, persistence). Format: command1 ; command2",
                    #"prompt": "SSH Honeypot. Predict next high value commands (download,exec,persist). Fmt: c1;c2",
                    #"prompt": "Role: Predictive Honeypot & Threat Analyst.\nTask: Analyze SSH session logs to predict the next high-value malicious command and configure a defensive trap.\nConstraints:\n1. Ignore navigation (ls, cd) unless relevant to reconnaissance.\n2. Output valid JSON only.\n\nAllowed Enums:\n- Intent: [reconnaissance, credential_harvesting, lateral_movement, persistence, exfiltration, privilege_escalation]\n- TrapAction: [create_file, monitor_execution, monitor_read, monitor_download]\n- TrapCategory: [aws_credentials, kube_config, wireguard, http_trap_script, sensitive_text_monitor, pdf_lure_context]\n- Token: [aws_id, kube_token, wireguard_conf, url_token, file_open_token, acrobat_reader_token]\n\nOutput Schema:\n[\n  {\n    \"predicted_cmd\": \"string\",\n    \"intent_category\": \"Intent enum\",\n    \"intent_description\": \"string\",\n    \"trap_action\": \"TrapAction enum\",\n    \"trap_path\": \"string\",\n    \"trap_template\": \"string\",\n    \"trap_category\": \"TrapCategory enum\",\n    \"trap_token_type\": \"Token enum\",\n    \"confidence_score\": float (0.0-1.0),\n    \"reasoning\": \"string\",\n    \"alternative_traps\": [{\"template\": \"string\", \"rationale\": \"string\"}]\n  }\n]",
                    "input": input_string,
                    "output": output_string
                }
                training_data.append(example)
                count_examples += 1
        print(f"[*] Generati {count_examples} esempi di training.")
        print(f"[*] Scrittura file output: {OUTPUT_FILE}")

        # Scrittura in formato JSON valido
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
            json.dump(training_data, out_f, ensure_ascii=False, indent=4)

        print("[*] Completato con successo.")

    except FileNotFoundError:
        print(f"[!] Errore: File {INPUT_FILE} non trovato.")
    except Exception as e:
        print(f"[!] Errore: {e}")

if __name__ == "__main__":

    # Controllo argomenti da linea di comando
    if len(sys.argv) < 2:
        print("Uso: python script.py <input_file.json>")
        sys.exit(0)

    # Prendo il primo argomento come file di input (può essere assoluto o relativo)
    INPUT_FILE = sys.argv[1]
    
    # Verifico che sia un file esistente e non una directory
    if not os.path.isfile(INPUT_FILE):
        print(f"[!] Errore: Il file '{INPUT_FILE}' non esiste o non è un file valido.")
        sys.exit(0)

    # 1. Estraggo solo il nome del file dal percorso (es. '/path/to/log.json' -> 'log.json')
    filename_only = os.path.basename(INPUT_FILE)
    
    # 2. Rimuovo l'estensione dal solo nome file (es. 'log.json' -> 'log')
    name_without_ext = os.path.splitext(filename_only)[0]
    
    # 3. Genero il nome di output (verrà salvato nella cartella corrente da dove lanci lo script)
    #OUTPUT_FILE = f'sliding_windows_{name_without_ext}.json'
    OUTPUT_FILE = f'sliding_windows_long_{name_without_ext}.json'
    
    # Variabili globali impostate, avvio il processo
    process_sliding_window()
