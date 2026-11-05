# Reproductor de sprites

`sprite-player.js` és un reproductor de PNG per a un canvas 2D. No conté un model d'IA ni crea una finestra transparent damunt de l'escriptori: aquestes parts pertanyen a l'aplicació que integri els sprites.

## Provar les animacions

Obre `../preview/preview.html` amb un navegador. És un únic fitxer amb les imatges incrustades, funciona sense connexió i no envia dades.

## Integració bàsica

Carrega `sprite-player.js` des d'una etiqueta `<script>`. En una aplicació web servida per HTTP local, pots carregar el manifest així:

```js
const manifest = await fetch('animations.json').then(response => response.json());
const sprite = await new SpiderSpritePlayer(manifest, {
  baseUrl: '', // Carpeta que conté animations.json i sheets/.
  animation: 'idle',
  onComplete: (name, next, player) => {
    if (next) player.setAnimation(next, { flipX: player.flipX });
  }
}).load();

const canvas = document.querySelector('canvas');
const context = canvas.getContext('2d');
let previousTime;

function frame(time) {
  const seconds = previousTime === undefined ? 0 : Math.min((time - previousTime) / 1000, 0.1);
  previousTime = time;
  sprite.update(seconds);
  context.clearRect(0, 0, canvas.width, canvas.height);
  sprite.draw(context, 200, 300, { scale: 2 });
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

El punt `(200, 300)` correspon al pivot declarat pel manifest: habitualment els peus per a animacions de terra i un punt diferent per a les de teranyina. El reproductor respecta el pivot de cada fotograma quan existeix. Les coordenades i el moviment per la pantalla els controla l'aplicació.

## Canviar l'estat visual

```js
sprite.setAnimation('walk');
sprite.setDirection('left');
sprite.setSpeed(1.25);

// Exemples de connexió amb esdeveniments del teu agent:
const visualStates = {
  microphone_active: 'listen',
  model_generating: 'think',
  tool_running: 'work',
  speech_playing: 'talk',
  task_succeeded: 'success',
  task_failed: 'error'
};

function onAgentEvent(eventName) {
  const animation = visualStates[eventName] || 'idle';
  sprite.setAnimation(animation, { flipX: sprite.flipX });
}
```

La màscara no té boca: la resposta es representa amb petits gestos i moviment del cos. No hi ha sincronització labial ni reconeixement de veu incorporats.

## API

| Mètode o propietat | Funció |
| --- | --- |
| `load()` | Carrega els fulls PNG i retorna una promesa del reproductor. |
| `setAnimation(id, options)` | Tria animació o àlies i reinicia la seqüència. `restart:false` evita reiniciar-la si ja era activa. |
| `setDirection('left' / 'right')` | Reflecteix horitzontalment al voltant del pivot. |
| `setSpeed(factor)` | Multiplica el ritme; `1` és el ritme del manifest i `0` pausa. |
| `update(seconds)` | Avança amb temps real, independentment dels FPS de la pantalla. |
| `draw(ctx, x, y, {scale})` | Dibuixa el fotograma actual sense suavitzat. |
| `seek(milliseconds)` | Col·loca el capçal en un instant de l'animació. |
| `current` | Fotograma, índex i pivot actuals. |
| `finished` | Indica si una animació sense bucle ha acabat. |
| `durationMs` | Durada d'un cicle segons els fotogrames i els FPS. |
| `localToWorld(point, x, y, scale)` | Converteix un punt del sprite en coordenades del canvas. |

Opcions de `setAnimation`: `flipX`, `reverse`, `loop` i `restart`. Un àlies pot declarar `animation`, `flipX` i `reverse`. El reproductor reutilitza els mateixos pixels per als sentits esquerre i dret.

Pots passar imatges ja carregades amb `{images: {sheetId: imageElement}}` o fonts incrustades amb `{imageSources: {sheetId: 'data:image/png;base64,...'}}`. Això evita `fetch()` i és útil en entorns locals amb restriccions de `file://`.

Per mantenir els píxels nítids, utilitza escales enteres i `imageSmoothingEnabled = false`. Les teranyines llargues, les col·lisions, les vores de pantalla, la gravetat i l'arrossegament s'han d'implementar al contenidor de l'agent; els sprites només representen la postura.
