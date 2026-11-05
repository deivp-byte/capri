# Spider-Man pixel art · Sprites per a un agent local

Pack de **30 animacions base i 180 fotogrames**, amb fons transparent, per donar moviment i personalitat a un assistent d’escriptori. El disseny és una adaptació de la foto de referència: cap vermell gran, ull blanc de perfil, contorn fosc i accents blau cian. Els sprites s’han generat amb l’eina integrada de generació d’imatges; són una reinterpretació de la referència, no una extracció exacta dels seus píxels.

## Veure les animacions

1. Descomprimeix el ZIP conservant les carpetes.
2. Obre **preview.html** al navegador.
3. Revisa les animacions i la demostració de moviment. La previsualització funciona localment, sense instal·lacions ni connexió a un model d’IA.

## Què inclou

| Grup | Animacions |
|---|---|
| Moviment a terra | Repòs, caminar, córrer, saltar, caure i aterrar. |
| Spider-Man | Escalar, quedar-se a la paret, avançar pel sostre, llançar teranyina, penjar-se cap per avall i balancejar-se. |
| Agent | Escoltar, pensar, treballar, respondre, celebrar i mostrar un error. |
| Interacció i descans | Saludar, seure, dormir, despertar-se, deixar-se arrossegar i treure el cap. |
| Gestos i transicions | Frenar, llegir, buscar, assenyalar, sorprendre’s i reaccionar en deixar-lo anar. |

- **sheets/**: cinc fulls PNG de 768 × 768 px, cadascun amb sis files i sis columnes. Cada fila és una animació.
- **frames/**: els 180 fotogrames individuals de 128 × 128 px, agrupats per animació.
- **animations/**: trenta tires PNG de 768 × 128 px, una per animació.
- **animations.json**: coordenades, pivots, FPS, durades especials, bucles, transicions i àlies.
- **preview.html**: demo interactiva autònoma. **animacions.gif**: mostra animada de sis estats.
- **runtime/**: reproductor JavaScript reutilitzable i exemples per connectar els estats de l’agent.
- **source_atlases/**: les cinc làmines originals de 1254 × 1254 px. Utilitza les exportacions de **sheets/** per tenir els fotogrames alineats.
- **GENERATION_PROMPTS.txt**: les descripcions utilitzades per generar les làmines.

Per conservar l’estètica, utilitza interpolació *nearest-neighbor* o `image-rendering: pixelated` i, preferiblement, escales enteres.

## Esquerra, dreta i variants

Els moviments direccionals tenen una orientació base. Els àlies amb sufix **_right** i **_left** reutilitzen els mateixos fotogrames mitjançant `flipX`; no representen dibuixos addicionals. Quan gires el personatge, també has de reflectir els seus punts d’ancoratge.

**climb_down** reutilitza `climb` amb l’ordre dels fotogrames invertit i desplaçament descendent. **web_descend** reutilitza `web_hang` mentre el motor augmenta la posició vertical. Aquestes variants s’obtenen per programari i no s’inclouen en el recompte de 30 animacions base.

## Connectar-lo al teu programa

Mantén separats el fotograma i la posició del personatge. El sprite canvia de postura; el teu motor controla les coordenades, la velocitat, la gravetat i els límits de la pantalla.

Utilitza el **pivot** com a punt de suport per evitar salts de posició entre estats. Per a les teranyines, dibuixa la línia des de l’ancoratge de pantalla fins al **webOrigin** del fotograma. Així la llargada s’adapta a qualsevol altura.

L’agent pot seleccionar `listen` quan escolta, `think` mentre prepara una resposta, `work` mentre executa una tasca i `talk` quan respon. `talk` es representa amb gestos del cap i dels braços, sense afegir una boca a la màscara.

En arrossegar-lo, activa `drag`, segueix el cursor i pausa la física. En deixar-lo anar, passa a `released` i després a `fall`; en tocar el terra, activa `land`. Les transicions físiques i les ordres de l’agent tenen prioritat sobre el camp `next` del manifest, que indica una continuació visual per defecte.

## Abast de la demostració

La previsualització inclou un motor JavaScript local limitat al navegador. Per moure aquest personatge per l’escriptori real, cal integrar els recursos en una aplicació amb finestra transparent i control de posició. La connexió a un model local, l’entrada de veu i l’execució de tasques corresponen a aquesta aplicació; el pack aporta les animacions i les dades per reproduir-les.
