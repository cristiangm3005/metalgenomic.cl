# Metalgenomic · pasos para aplicar todas las mejoras

Orden recomendado. Cada paso dice qué hacer, dónde y cómo comprobar que quedó bien.
Archivos de esta carpeta: `metalgenomic-landing-elementor-pro-v12.json` (landing), `metalgenomic-privacidad-elementor.json` (privacidad), `metalgenomic-formulario.zip` (plugin del formulario), `robots.txt`.

---

## Antes de empezar · Razón social

El certificado del Registro de Empresas y Sociedades (emitido el 10 de noviembre de 2026) dice:

| Dato | Hoy en el Registro | En el sitio web |
|---|---|---|
| Razón social | Genomic Complexity SpA | Genomic Industries SpA |
| RUT | 77.958.319-8 | 77.958.319-8 |
| Domicilio | Copiapó, Región de Atacama | Copiapó, Región de Atacama |

El sitio y la política de privacidad ya dicen «Genomic Industries SpA · RUT 77.958.319-8». El RUT no cambia al modificar el nombre de la sociedad.

### Paso 0 · Cambiar la razón social a Genomic Industries SpA
1. Entra a **registrodeempresasysociedades.cl** con tu ClaveÚnica.
2. Elige la sociedad Genomic Complexity SpA y la actuación **Modificación** de estatutos.
3. Cambia el Artículo Primero (nombre) a «Genomic Industries SpA», y el nombre de fantasía si lo usas.
4. Firma con tu firma electrónica avanzada o ClaveÚnica, según lo pida el sistema.
5. Descarga el nuevo **Certificado de Estatuto Actualizado**: te servirá para la carpeta de proveedor (paso 13).
6. Revisa en **sii.cl** que la sociedad aparezca con el nuevo nombre. Si no aparece, actualiza los datos con el SII.

**Listo cuando:** el nuevo certificado dice «Razón Social: GENOMIC INDUSTRIES SpA». Publica la web (fase 1) recién después de esto, para que el pie y la política de privacidad nombren a una sociedad que ya existe con ese nombre.

---

## Fase 1 · Publicar la web nueva (≈ 1 hora)

### Paso 1 · Respaldo
1. Instala **UpdraftPlus** (si no lo tienes) y haz un respaldo completo: Ajustes → UpdraftPlus → «Respaldar ahora».
2. En Elementor → Plantillas, exporta la página actual por si necesitas volver atrás.

**Listo cuando:** ves el respaldo en la lista de UpdraftPlus.

### Paso 2 · Importar la landing v12
1. Elementor → Plantillas → **Importar plantillas** → sube `metalgenomic-landing-elementor-pro-v12.json`.
2. Abre la página de inicio con Elementor, borra el contenido anterior y usa el ícono de carpeta → «Mis plantillas» → inserta «Metalgenomic · Landing 3D (v12)».
3. En Ajustes de la página (engranaje), plantilla: **Elementor Canvas**.
4. Actualiza.

**Listo cuando:** la portada naranja se ve en el sitio y, al deslizar, aparece la escena 3D.

### Paso 3 · Revisar el RUT
El RUT 77.958.319-8 ya viene escrito en las plantillas: en el pie, en la portada y en la política de privacidad. Solo revisa que se vea.

**Listo cuando:** el pie dice «Metalgenomic es una marca de Genomic Industries SpA · RUT 77.958.319-8».

### Paso 4 · Página de privacidad
1. Páginas → Añadir nueva → título «Política de privacidad», **slug `privacidad`**.
2. Edita con Elementor, plantilla **Elementor Canvas**, inserta «Metalgenomic · Política de privacidad» (importada igual que en el paso 2).
3. Envía el texto a un abogado para revisión antes de anunciarla. La Ley 21.719 rige desde el 1 de diciembre de 2026.

**Listo cuando:** `metalgenomic.cl/privacidad/` abre la política y el enlace del formulario lleva a ella.

### Paso 5 · Recepción del formulario (llega a contacto@metalgenomic.cl)
El formulario envía cada solicitud a tu propio WordPress, y este la manda a contacto@metalgenomic.cl. Para eso se usa un plugin pequeño hecho para la web, `metalgenomic-formulario.zip`.
1. En WordPress ve a **Plugins → Añadir nuevo → Subir plugin**, elige `metalgenomic-formulario.zip` y pulsa **Instalar ahora**, luego **Activar**.
2. Instala y activa **FluentSMTP** (Plugins → Añadir nuevo → busca «FluentSMTP»). En su asistente, elige la conexión del correo de tu hosting (SMTP de cPanel) con la cuenta contacto@metalgenomic.cl. Usa la prueba de envío del plugin para confirmar que funciona.
3. En el menú de WordPress aparece **Solicitudes**: ahí queda una copia de cada solicitud, aunque el correo falle.
4. Abre el sitio publicado en modo incógnito, completa el formulario de «Agendar» y envíalo.

Qué incluye el plugin:
- El botón «Responder» de tu correo contesta directo a quien escribió.
- Un campo invisible que detiene a los robots de spam.
- Un máximo de 5 envíos cada 10 minutos por visitante.
- Si el plugin no está activo o el correo falla, el formulario le ofrece al visitante enviar el mensaje desde su propio correo, así no se pierde el contacto.

**Listo cuando:** ves «Recibimos tu solicitud», el correo llega a contacto@metalgenomic.cl y la solicitud aparece en **Solicitudes**.

Si usas Wordfence u otro plugin de seguridad, no bloquees la «API REST» para visitantes: el formulario la necesita.

---

## Fase 2 · Velocidad y fluidez del 3D (≈ 30 min)

La v12 ya trae estas optimizaciones dentro del código:

| Mejora | Efecto |
|---|---|
| three.js empieza a descargarse apenas se lee la página (preload) | La escena está lista antes |
| La escena se arma cuando el navegador terminó de pintar la portada | La portada aparece sin trabas |
| Los efectos de imagen (bloom, profundidad, nitidez) llegan después del primer cuadro | Primer cuadro más rápido |
| En celulares y equipos modestos no se usan esos efectos | Menos consumo de batería y menos calor; más cuadros por segundo |
| El 3D no se dibuja mientras la portada naranja lo tapa | La GPU queda libre al cargar |
| Las posiciones de las secciones se guardan en memoria | El scroll no obliga al navegador a recalcular la página en cada cuadro |
| La escena se arma en trozos y los shaders se compilan en paralelo | La página sigue respondiendo mientras carga el 3D |
| En celular, la barra del navegador ya no redimensiona el 3D al deslizar | Sin tirones al subir y bajar |
| Con «reducir movimiento» activado en el sistema, los textos ya no se superponen | Accesibilidad |

**Medido en pruebas (navegador sin GPU, sirve para comparar, no como valor absoluto):**

| | Antes (v10) | Ahora (v12) |
|---|---|---|
| Escena 3D lista, escritorio | 2,2–2,4 s | 1,6–1,8 s |
| Escena 3D lista, celular | 2,0–2,1 s | 1,2–1,4 s |
| Tiempo bloqueado al cargar, celular | 1,3–1,5 s | 0,6–0,7 s |
| Archivos de three.js, celular | 21 | 6 |

La escena se ve igual que antes: comparé 9 vistas píxel a píxel.

### Paso 6 · Configurar la caché sin romper el 3D
En **LiteSpeed Cache** o **WP Rocket**:
1. Activa la caché de página y la compresión (GZIP/Brotli).
2. **No** actives «Retrasar JavaScript» (Delay JS) ni «Combinar JS» para la página de inicio. Si quieres usarlos en el resto del sitio, agrega a las exclusiones: `three`, `gsap`, `MGScene`, `__mg`.
3. No actives «Minificar HTML» agresivo en la página de inicio.
4. Si tu plugin ofrece «Precargar fuentes de Google» o «Alojar Google Fonts localmente», actívalo.

**Listo cuando:** la página carga en modo incógnito y al deslizar aparece el 3D.

### Paso 7 · Comprobar el 3D
1. Abre `metalgenomic.cl/?mgdebug=1`. Abajo a la izquierda aparece el estado del motor: debe decir «activo».
2. Prueba en un celular real: desliza toda la página; los textos deben entrar y salir con el mismo ritmo.
3. Mide en **PageSpeed Insights** (pagespeed.web.dev) la versión móvil y la de escritorio. Guarda la nota para comparar después.

Parámetros útiles para diagnosticar (se agregan a la URL):
- `?gl=0`: sin 3D (fondo estático).
- `?fx=0`: 3D sin efectos de imagen.
- `?fx=1`: fuerza los efectos también en celular.

---

## Fase 3 · SEO y presencia (≈ 1 hora)

### Paso 8 · Rank Math
1. Instala **Rank Math** y sigue el asistente (tipo: empresa; nombre: **Metalgenomic**).
2. En la página de inicio → Rank Math → Editar fragmento:
   - Título: `Metalgenomic · Biolixiviación genómica y BIM para minería del cobre`
   - Descripción: `Diagnóstico de biolixiviación genómica y modelo BIM de planta para minería del cobre, en hasta 4 semanas. Primera reunión sin costo y NDA. Copiapó, Chile.`
3. Rank Math → Sitemap: activado. Comprueba que `metalgenomic.cl/sitemap_index.xml` abre.
4. Rank Math → Ajustes generales → Editar robots.txt: pega el contenido de `robots.txt`.

### Paso 9 · Google Search Console
1. Agrega la propiedad `metalgenomic.cl` y verifícala (Rank Math lo facilita).
2. Envía `sitemap_index.xml`.

### Paso 10 · LinkedIn e INAPI
1. Crea la página de empresa **Metalgenomic** en LinkedIn (mismo nombre, mismo logo, enlace a la web).
2. Publica un artículo técnico al mes (por ejemplo: qué mide un análisis metagenómico de pila).
3. Usa «Metalgenomic» también en la solicitud de marca en INAPI.

---

## Fase 4 · Respaldo del negocio (semanas)

Estos pasos no se resuelven en la web, pero el sitio ya está redactado para reflejarlos cuando estén listos.

### Paso 11 · Equipo
1. Define quiénes son las personas o asesores reales (biotecnología, geología, datos).
2. Pide permiso a cada uno para publicar nombre, cargo y LinkedIn.
3. Envíamelos y agrego una sección «Equipo» a la landing.

### Paso 12 · Laboratorio de secuenciación
1. Cotiza con al menos dos laboratorios (uno universitario y uno comercial).
2. Firma un acuerdo que incluya: protocolo de toma y envío de muestras, cadena de custodia, plazos y **propiedad de los datos genómicos del cliente**.
3. Cuando esté firmado, puedo nombrar al laboratorio aliado en el sitio.

### Paso 13 · Carpeta de proveedor minero
Ten listos, en PDF:
- Certificado de vigencia y de estatuto actualizado de Genomic Industries SpA (el nuevo, después del paso 0).
- Carpeta tributaria (SII).
- Póliza de seguro de responsabilidad civil.
- Registro en la plataforma de proveedores del cliente (pregunta cuál usa su área de abastecimiento).
- Para trabajar en faena: inducción de seguridad y cobertura de accidentes del trabajo (mutualidad).

### Paso 14 · Matriz (genomicindustries.com)
Respalda con literatura científica la frase «Más recuperación, menos impacto ambiental», o quítala hasta tener un piloto propio con cifras.

### Paso 15 · Habilitar las líneas secundarias
Cuando tengas el aliado geoespacial firmado o el piloto de mantenimiento predictivo listo, avísame para quitar las etiquetas «Con aliados» o «Próximamente».

---

## Lista final de verificación

- [ ] Razón social cambiada a Genomic Industries SpA (Registro y SII)
- [ ] Respaldo hecho
- [ ] Landing v12 publicada y 3D «activo» con `?mgdebug=1`
- [ ] RUT 77.958.319-8 visible en el pie y en la privacidad
- [ ] `/privacidad/` publicada y revisada por un abogado
- [ ] Plugin del formulario y FluentSMTP activos
- [ ] Solicitud de prueba recibida en contacto@metalgenomic.cl y visible en «Solicitudes»
- [ ] Caché configurada sin «Delay JS» en la página de inicio
- [ ] Título SEO, sitemap y robots.txt activos
- [ ] Search Console con el sitemap enviado
- [ ] Página de LinkedIn creada
- [ ] Equipo, laboratorio y carpeta de proveedor en curso
