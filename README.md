# TAF Italia - QGIS Plugin

![QGIS Minimum Version](https://img.shields.io/badge/QGIS-3.10%2B-green?logo=qgis)
![License](https://img.shields.io/badge/License-GPL%20v2-blue.svg)
![Release](https://img.shields.io/badge/Version-2.5.1-orange)

**TAF Italia** è un plugin per QGIS progettato per semplificare e automatizzare il lavoro dei professionisti tecnici italiani (geometri, ingegneri, architetti, periti) che operano in ambito catastale e topografico. 
Il plugin permette di scaricare automaticamente gli archivi dei **Punti Fiduciali (TAF)** direttamente dai server dell'Agenzia delle Entrate, convertirli dai sistemi nativi (Cassini-Soldner o Gauss-Boaga) nel sistema globale WGS84 (EPSG:4326) e caricarli istantaneamente in QGIS pronti per l'uso.

![Screenshot del Plugin](TAF.png)

## ✨ Funzionalità Principali

- **Download Diretto e Sicuro**: Scarica i dati TAF aggiornati direttamente dall'Agenzia delle Entrate, gestendo in automatico le connessioni e gli eventuali ritardi dei server statali.
- **Riconoscimento Automatico CRS**: Identifica il sistema di coordinate di partenza analizzando i valori delle coordinate (soglie Gauss-Boaga Ovest/Est, Cassini-Soldner).
- **Conversione Accurata in WGS84**: 
  - Da *Gauss-Boaga* (EPSG 3003/3004) a *WGS84* (EPSG 4326) usando le librerie standard.
  - Da *Cassini-Soldner* a *WGS84* usando parametri matematici complessi (Bursa-Wolf Rome 40).
- **Integrazione Immediata in QGIS**: Carica i dati estratti direttamente nel progetto corrente come layer GeoPackage (GPKG) o testuale (CSV), senza bisogno di passaggi manuali.
- **Tematizzazione Automatica (Stile)**: Applica in automatico uno stile predefinito (simbolo a triangolo verde tipico dei punti fiduciali) e abilita le etichette con il nome del punto (es. `PF01/0010/A234`).
- **Azione "Monografia" Rapida**: Aggiunge un'Azione di QGIS che permette, cliccando su un Punto Fiduciale in mappa, di aprire direttamente nel browser la pagina per scaricare la relativa monografia.
- **Gestione Origini Locali**: Per i punti storici in Cassini-Soldner, include un editor visivo per inserire o modificare l'origine catastale (Emanazione) specifica del comune, migliorando l'accuratezza rispetto all'uso delle sole Grandi Origini provinciali.

## 🚀 Installazione

### Via QGIS Plugin Repository (Consigliato)
1. Aprire QGIS.
2. Andare su **Plugin > Gestisci e Installa Plugin...**
3. Cercare **TAF Italia** e cliccare su **Installa Plugin**.

### Installazione Manuale (da file ZIP)
1. Scaricare l'ultima release in formato `.zip` dalla pagina [Releases](https://github.com/sag1687/TAF_ITALIA_DOWNLOAD/releases) (se disponibile) o scaricare il codice sorgente tramite il pulsante **Code > Download ZIP**.
2. Aprire QGIS.
3. Andare su **Plugin > Gestisci e Installa Plugin... > Installa da ZIP**.
4. Selezionare il file scaricato e confermare.

## 💻 Guida all'Uso

1. Aprire il plugin dalla barra degli strumenti o dal menu **Web > TAF Italia**.
2. **Selezionare la Provincia** di interesse dal menu a tendina.
3. *(Opzionale)* Personalizzare la directory di salvataggio dei file elaborati.
4. *(Opzionale)* Configurare eventuali **Origini Locali** usando l'apposito editor se si lavora in aree con sistemi Cassini-Soldner specifici e si necessita di alta precisione.
5. Cliccare su **Scarica ed Elabora**.
6. Il plugin elaborerà i file: al termine dell'elaborazione comparirà automaticamente il layer vettoriale sulla mappa.
7. Usare lo strumento di "Informazioni Elementi" (o le Azioni QGIS attivate col tasto destro) per cliccare su un punto ed aprire rapidamente la **Monografia** associata dal sito dell'Agenzia delle Entrate.

---

## 🛠 Analisi Tecnica — Ha senso? Funziona?

**Sì, il plugin è tecnicamente valido e risolve un problema reale.** Ogni giorno tecnici catastali, geometri e ingegneri in Italia devono scaricare e lavorare con i Punti Fiduciali. Il flusso ufficiale (browser Agenzia Entrate → TAF → conversione manuale con tool esterni → QGIS) è lento e ripetitivo. Questo plugin automatizza tutto con pochi click.

### Cosa funziona correttamente

- **Download HTTP**: usa session requests con retry e backoff, gestisce server non responsivi e content-type HTML (assenza dati). La logica di resume evita download ripetuti.
- **Riconoscimento CRS**: le soglie sui valori di Est (GB Ovest 1.3M–1.9M, GB Est 2.3M–2.9M, Cassini <500K) sono empiriche ma consolidate nella pratica catastale italiana.
- **Conversione Gauss-Boaga → WGS84**: usa i codici EPSG ufficiali (3003/3004 → 4326) tramite pyproj/PROJ. La trasformazione è esatta perché i parametri sono standardizzati.
- **Conversione Cassini-Soldner → WGS84**: formula matematica corretta (proiezione Cassini su ellissoide Bessel 1841). I parametri Bursa-Wolf (`-104.1,-49.1,-9.9,0.971,-2.917,0.714,-11.68`) sono il set Rome 40 → WGS84, adeguato per l'Italia peninsulare con accuratezza metrica.
- **Architettura QGIS**: Utilizza un `QgsTask` asincrono per non bloccare l'interfaccia utente durante il download, supporta segnali `progressChanged`/`taskCompleted`/`taskTerminated`, compatibilità nativa tra PyQt5 e PyQt6.
- **Generazione GPKG nativa**: usa `QgsVectorFileWriter.writeAsVectorFormatV3` senza dipendenze esterne (es. no geopandas, no pandas, no shapely).
- **Tematizzazione automatica**: renderer triangolare, labeling, action per apertura monografia via browser — tutto implementato via API QGIS standard.

### Limitazioni tecniche note e Risoluzioni

1. **Origini Cassini-Soldner**: Il catasto storico italiano conta oltre 818 centri di emanazione (piccole origini). Il plugin usa per default 31 Grandi Origini raggruppate per provincia. Usare un'origine provinciale per punti di un comune che afferisce a una piccola origine diversa può produrre scostamenti di decine di metri. **Soluzione**: l'editor "Origini Locali" integrato nel plugin permette di inserire l'origine esatta del proprio comune (se nota).
2. **Parametri Bursa-Wolf fissi**: Il set Rome 40 non è ottimale per tutto il territorio nazionale (es. Sicilia e Sardegna hanno datum locali diversi). Per un lavoro di precisione catastale sub-metrica servirebbero parametri regionali.
3. **Soglie di rilevamento CRS**: Se un valore di Est cade esattamente al confine tra due sistemi (es. ~1.3M o ~2.3M), il riconoscimento potrebbe essere ambiguo. I TAF storici con coordinate Cassini non dovrebbero superare 500 km dal centro di emanazione, ma non è garantito in caso di errori nei dati nativi.
4. **Affidabilità server ADE**: I server dell'Agenzia delle Entrate non hanno garanzie di uptime. Il plugin gestisce i timeout ma non può aggirare l'indisponibilità totale del servizio.

### Casi d'uso reali

- **Professionisti tecnici**: geometri e ingegneri che devono quotidianamente scaricare TAF per aggiornamento catastale e rilievi.
- **Studi associati**: decine di comuni gestiti, dove l'automazione del download fa risparmiare molte ore.
- **Formazione e didattica**: laboratori GIS su dati catastali reali.

### Conclusione

Il plugin non è un software di certificazione metrica, ma un **tool operativo che automatizza il workflow TAF**. Per usi tecnici ordinari (accuratezza sub-decimetrica non richiesta, inquadramenti di massima, sopralluoghi, planimetrie, allineamento catastale rapido) è pienamente funzionante e sufficiente. Per certificazioni metriche di altissima precisione, verificare e applicare sempre le origini Cassini-Soldner locali e i parametri di trasformazione specifici assistiti da un geodeta o specialista abilitato.

## 📋 Requisiti

- **QGIS 3.10** o superiore (testato ed ottimizzato per compatibilità anche su QGIS 4.x / PyQt6)
- Connessione a Internet attiva (per il download dei dati dall'ADE)
- *Nessun plugin o libreria esterna richiesto!* Il plugin fa uso interamente delle potenti API native di QGIS e Python.

## 👨‍💻 Autore e Crediti

Sviluppato da **Dott. Sarino Alfonso Grande** — [sinocloud.it](https://sinocloud.it)  
I dati catastali manipolati sono di titolarità dell'Agenzia delle Entrate italiana.

*Questo plugin è stato scritto e rivisto con l'ausilio dell'intelligenza artificiale.*

## 📄 Licenza

Rilasciato sotto licenza open-source [GNU General Public License (GPL) version 2](LICENSE).
