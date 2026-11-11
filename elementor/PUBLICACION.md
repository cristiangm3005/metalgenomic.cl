# Metalgenomic · guía de publicación

Sigue los pasos en orden. Cada uno dice dónde hacer clic y cómo comprobar que quedó bien. Tiempo total: unas 2 horas.

## Antes de empezar

### Ten a mano estos archivos
| Archivo | Para qué sirve |
|---|---|
| metalgenomic-landing-elementor-pro-v12.json | La página de inicio completa |
| metalgenomic-privacidad-elementor.json | La página de política de privacidad |
| metalgenomic-formulario.zip | El plugin que envía el formulario a contacto@metalgenomic.cl |
| robots.txt | El texto para el archivo robots.txt |

**No descomprimas** el archivo `metalgenomic-formulario.zip`: WordPress lo necesita tal cual.

### Ten a mano estos accesos
- Usuario y contraseña de **administrador de WordPress** (metalgenomic.cl/wp-admin).
- Acceso a **cPanel** de tu hosting.
- Tu **cuenta de Google** (para Search Console).

### Revisa la razón social
El sitio dice «Metalgenomic es una marca de Genomic Industries SpA · RUT 77.958.319-8». Hoy la sociedad está registrada como **Genomic Complexity SpA**. Haz el cambio de nombre en registrodeempresasysociedades.cl **antes del paso 18** (publicar). Mientras tanto puedes avanzar con todo lo demás.

## Parte 1 · Preparar WordPress (≈ 20 min)

### Paso 1 · Hacer un respaldo
1. En WordPress ve a **Plugins → Añadir nuevo**, busca **UpdraftPlus**, pulsa **Instalar ahora** y luego **Activar**.
2. Ve a **Ajustes → Copias de seguridad UpdraftPlus** y pulsa **Respaldar ahora**. Deja marcadas las opciones de base de datos y archivos.

**Listo cuando:** el respaldo aparece en la lista «Copias de seguridad existentes».

### Paso 2 · Crear el correo contacto@metalgenomic.cl (si no existe)
1. En cPanel abre **Cuentas de correo electrónico**.
2. Si no ves contacto@metalgenomic.cl, pulsa **Crear**, escribe `contacto` y una contraseña segura. Guárdala: la usarás en el paso 6.
3. Junto a la cuenta pulsa **Conectar dispositivos** (o «Configurar cliente de correo») y anota los datos del **servidor de salida (SMTP)**: servidor (normalmente `mail.metalgenomic.cl`), puerto (normalmente `465`) y tipo de seguridad (SSL).

**Listo cuando:** puedes entrar a la cuenta desde **Webmail**.

### Paso 3 · Revisar los enlaces permanentes
1. Ve a **Ajustes → Enlaces permanentes**.
2. Elige **Nombre de la entrada** (si no está elegido) y pulsa **Guardar cambios**.

**Listo cuando:** se guardó sin errores.

## Parte 2 · Instalar los plugins (≈ 20 min)

### Paso 4 · Plugin del formulario
1. Ve a **Plugins → Añadir nuevo → Subir plugin**.
2. Pulsa **Elegir archivo**, selecciona `metalgenomic-formulario.zip` y pulsa **Instalar ahora**.
3. Pulsa **Activar plugin**.

**Listo cuando:** en el menú izquierdo aparece **Solicitudes**.

### Paso 5 · Instalar FluentSMTP
1. Ve a **Plugins → Añadir nuevo**, busca **FluentSMTP**, instálalo y actívalo.

**Listo cuando:** aparece **Ajustes → FluentSMTP**.

### Paso 6 · Conectar FluentSMTP con tu correo
1. Ve a **Ajustes → FluentSMTP** y pulsa para agregar una conexión.
2. Elige **Other SMTP** (otro SMTP).
3. Completa:
   - Correo del remitente (From Email): `contacto@metalgenomic.cl`
   - Nombre del remitente (From Name): `Metalgenomic`
   - Servidor SMTP: el del paso 2 (por ejemplo, `mail.metalgenomic.cl`)
   - Puerto: `465`
   - Encriptación: **SSL**
   - Usar autenticación: **Sí**
   - Usuario: `contacto@metalgenomic.cl`
   - Contraseña: la del paso 2
4. Guarda.
5. Ve a la pestaña **Email Test** (prueba de correo), envía una prueba a contacto@metalgenomic.cl y revísala en Webmail.

**Listo cuando:** el correo de prueba llega (revisa también la carpeta de spam).

### Paso 7 · Instalar Rank Math
1. Ve a **Plugins → Añadir nuevo**, busca **Rank Math SEO**, instálalo y actívalo.
2. Se abre el asistente. Elige el modo **Fácil**.
3. Tipo de sitio: **Otra web de la empresa**.
4. Nombre: `Metalgenomic`. Sube el logo si lo tienes.
5. Avanza con las opciones que vienen marcadas. Cuando pregunte por el **sitemap**, déjalo **activado**.
6. Puedes omitir la conexión con la cuenta de Rank Math y con Google por ahora (se hace en la parte 5).

**Listo cuando:** aparece el menú **Rank Math SEO**.

## Parte 3 · Subir las páginas (≈ 30 min)

### Paso 8 · Importar las dos plantillas
1. Ve a **Plantillas → Plantillas guardadas** (en versiones antiguas: **Elementor → Mis plantillas**).
2. Pulsa **Importar plantillas** (arriba).
3. Elige `metalgenomic-landing-elementor-pro-v12.json` y pulsa **Importar ahora**.
4. Repite con `metalgenomic-privacidad-elementor.json`.

**Listo cuando:** en la lista ves «Metalgenomic · Landing 3D (v12)» y «Metalgenomic · Política de privacidad».

### Paso 9 · Crear la página de privacidad
1. Ve a **Páginas → Añadir nueva**.
2. Título: `Política de privacidad`.
3. En el panel derecho, en **Enlace** (o «Slug»), escribe `privacidad`.
4. Pulsa **Editar con Elementor**.
5. Abre la configuración de la página (ícono de engranaje) y en **Diseño de página** elige **Elementor Canvas**.
6. Pulsa el ícono de carpeta (**Añadir plantilla**) → pestaña **Mis plantillas** → **Insertar** en «Metalgenomic · Política de privacidad».
7. Pulsa **Publicar**.

**Listo cuando:** metalgenomic.cl/privacidad/ muestra la política con fondo oscuro.

### Paso 10 · Crear la página de inicio
1. Ve a **Páginas → Añadir nueva**. Título: `Inicio`.
2. Pulsa **Editar con Elementor**.
3. Engranaje → **Diseño de página** → **Elementor Canvas**.
4. Ícono de carpeta → **Mis plantillas** → **Insertar** en «Metalgenomic · Landing 3D (v12)».
5. Pulsa **Publicar**.

Dentro del editor puede verse distinto o sin 3D: es normal. Revisa siempre con **Vista previa** o en el sitio.

**Listo cuando:** al abrir la página ves la portada naranja «Del dato al cátodo» y, al deslizar, la escena 3D.

### Paso 11 · Dejarla como página principal
1. Ve a **Ajustes → Lectura**.
2. En «Tu página de inicio muestra», elige **Una página estática**.
3. En **Página de inicio** elige `Inicio`. Pulsa **Guardar cambios**.
4. Si había una página de inicio anterior, déjala en borrador o en la papelera para que no compita en Google.

**Listo cuando:** metalgenomic.cl abre directamente la portada naranja.

### Paso 12 · Regenerar los estilos de Elementor
1. Ve a **Elementor → Herramientas** (o «Ajustes → Herramientas»).
2. Pulsa **Regenerar archivos y datos** (Regenerate CSS & Data) y **Guardar**.

**Listo cuando:** la página se ve igual en una ventana de incógnito.

## Parte 4 · Probar el formulario (≈ 10 min)

### Paso 13 · Enviar una solicitud de prueba
1. Abre metalgenomic.cl en una **ventana de incógnito**.
2. Baja hasta «¿Qué problema quieres resolver primero?» y completa el formulario con tus datos.
3. Marca la casilla de la política de privacidad y pulsa **Enviar solicitud**.

**Listo cuando:** se cumplen las tres cosas:
- la página muestra «Recibimos tu solicitud»;
- el correo llega a contacto@metalgenomic.cl (revisa spam) con el asunto «Diagnóstico operativo · …»;
- la solicitud aparece en el menú **Solicitudes** de WordPress.

Si la página dice «No pudimos enviarlo»: revisa que el plugin del paso 4 esté activo y que tu plugin de seguridad no bloquee la «API REST». Si el correo no llega pero la solicitud sí aparece en **Solicitudes**, revisa FluentSMTP (paso 6).

## Parte 5 · Google (≈ 30 min)

### Paso 14 · Título y descripción para Google
1. Abre la página **Inicio** para editar (con el editor de WordPress o con Elementor).
2. Pulsa el ícono de **Rank Math** → pestaña **General** → **Editar fragmento**.
3. Título: `Metalgenomic · Biolixiviación genómica y BIM para minería del cobre`
4. Descripción: `Diagnóstico de biolixiviación genómica y modelo BIM de planta para minería del cobre, en hasta 4 semanas. Primera reunión sin costo y NDA. Copiapó, Chile.`
5. Cierra y pulsa **Actualizar**.

**Listo cuando:** la vista previa de Rank Math muestra ese título y esa descripción.

### Paso 15 · robots.txt y sitemap
1. Ve a **Rank Math SEO → Ajustes generales → Editar robots.txt**.
2. Borra lo que haya y pega el contenido del archivo `robots.txt`. Guarda.
3. Abre metalgenomic.cl/robots.txt y metalgenomic.cl/sitemap_index.xml en el navegador.

**Listo cuando:** las dos direcciones abren. Si el sitemap da error, repite el paso 3.

### Paso 16 · Google Search Console
1. Entra a search.google.com/search-console y agrega una propiedad de tipo **Dominio**: `metalgenomic.cl`.
2. Google te da un texto que empieza con `google-site-verification=`. Cópialo.
3. En cPanel abre **Zone Editor** → **Administrar** en metalgenomic.cl → **Añadir registro TXT**:
   - Nombre: `metalgenomic.cl.`
   - Registro: el texto copiado
4. Guarda, vuelve a Search Console y pulsa **Verificar** (si falla, espera una hora y reintenta).
5. En el menú izquierdo, **Sitemaps** → escribe `sitemap_index.xml` → **Enviar**.

**Listo cuando:** la propiedad está verificada y el sitemap aparece como «Correcto» (puede tardar un día).

## Parte 6 · Velocidad (≈ 15 min)

### Paso 17 · Configurar la caché
Usa **LiteSpeed Cache** si tu hosting es LiteSpeed (pregúntale al soporte o mira en cPanel). Si no, **WP Rocket**. Instala solo uno.
1. Activa la **caché de páginas** y la **compresión** (GZIP o Brotli).
2. **No actives** «Retrasar JavaScript» (Delay JS), «Combinar JS» ni «Cargar JS diferido» para la página de inicio. Si los usas en otras páginas, excluye estas palabras: `three`, `gsap`, `MGScene`, `__mg`.
3. No actives la minificación agresiva del HTML.
4. Después de guardar, **vacía la caché**.

**Listo cuando:** en una ventana de incógnito la portada carga, el 3D aparece al deslizar y el formulario sigue funcionando (repite el paso 13).

## Parte 7 · Revisión final (≈ 15 min)

### Paso 18 · Revisar en computador y celular
1. Abre `metalgenomic.cl/?mgdebug=1`. Abajo a la izquierda debe decir «activo».
2. En un **celular real**, recorre toda la página: la portada, el 3D al deslizar, el formulario y el pie.
3. Revisa que el pie diga «Metalgenomic es una marca de Genomic Industries SpA · RUT 77.958.319-8» (solo si ya hiciste el cambio de razón social).
4. Mide en **pagespeed.web.dev** la versión para celular y para computador. Guarda las notas para comparar después.

**Listo cuando:** todo se ve bien y no hay nada roto.

### Paso 19 · Respaldo final
1. Vuelve a **UpdraftPlus** y pulsa **Respaldar ahora**.
2. En UpdraftPlus → **Ajustes**, programa respaldos **semanales** y guárdalos en Google Drive o Dropbox.

**Listo cuando:** ves el respaldo nuevo en la lista.

## Si algo sale mal
| Problema | Qué hacer |
|---|---|
| La página se ve en blanco o desordenada | Paso 12 (regenerar estilos) y vaciar la caché |
| No aparece el 3D | Abre `metalgenomic.cl/?mgdebug=1` y mira el mensaje. Si dice «no se pudo cargar», revisa el paso 17 (no retrasar ni combinar JS) |
| El formulario dice «No pudimos enviarlo» | Plugin del paso 4 activo; plugin de seguridad sin bloquear la API REST |
| El correo no llega | Paso 6 (FluentSMTP) y carpeta de spam; la solicitud igual queda en **Solicitudes** |
| /privacidad/ da error 404 | Paso 3 (guardar enlaces permanentes) |
| Quiero volver atrás | UpdraftPlus → **Restaurar** el respaldo del paso 1 |

## Lista de verificación
- [ ] Respaldo inicial hecho (paso 1)
- [ ] Correo contacto@metalgenomic.cl creado (paso 2)
- [ ] Plugin del formulario activo (paso 4)
- [ ] FluentSMTP conectado y correo de prueba recibido (pasos 5 y 6)
- [ ] Rank Math instalado (paso 7)
- [ ] Página de privacidad publicada en /privacidad/ (paso 9)
- [ ] Página de inicio publicada y como portada (pasos 10 y 11)
- [ ] Solicitud de prueba recibida y visible en «Solicitudes» (paso 13)
- [ ] Título, descripción, robots.txt y sitemap listos (pasos 14 y 15)
- [ ] Search Console verificado y sitemap enviado (paso 16)
- [ ] Caché configurada sin romper el 3D (paso 17)
- [ ] Revisión en celular y PageSpeed (paso 18)
- [ ] Razón social cambiada a Genomic Industries SpA
- [ ] Respaldos semanales programados (paso 19)
