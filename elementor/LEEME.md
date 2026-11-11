# Metalgenomic · plantillas Elementor (v12)

**Guía completa paso a paso: [`PASOS.md`](PASOS.md).**

## Archivos

| Archivo | Qué es |
|---|---|
| `metalgenomic-landing-elementor-pro-v12.json` | Landing completa: 3D optimizado y formulario que llega a contacto@metalgenomic.cl. **Usar esta.** |
| `plugin/metalgenomic-formulario.zip` | Plugin de WordPress que recibe el formulario y lo envía a contacto@metalgenomic.cl. |
| `metalgenomic-landing-elementor-pro-v11.json` | Versión anterior (formulario solo por correo del visitante). |
| `metalgenomic-landing-elementor-pro-v10.json` | Versión anterior (mismo contenido, sin optimización 3D). Solo como respaldo. |
| `metalgenomic-privacidad-elementor.json` | Página de política de privacidad. Publicar con el slug `/privacidad/`. |
| `robots.txt` | Contenido recomendado para robots.txt. |

## Pasos para publicar

1. **Importar** ambas plantillas: Elementor → Plantillas → Importar.
2. **Página de privacidad**: crear una página llamada «Política de privacidad», slug `privacidad`, plantilla *Elementor Canvas*, e insertar la plantilla. La landing ya enlaza a `/privacidad/` desde el formulario, el afiche y el pie.
3. **RUT y razón social**: el RUT 77.958.319-8 ya está incluido. Antes de publicar, cambia la razón social de «Genomic Complexity SpA» a «Genomic Industries SpA» en el Registro de Empresas y Sociedades (ver paso 0 de `PASOS.md`).
4. **Revisión legal**: la política está redactada según la Ley 19.628 y la Ley 21.719. Pídele a un abogado que la revise antes de publicarla.
5. **Formulario**: instala y activa `plugin/metalgenomic-formulario.zip` (Plugins → Añadir nuevo → Subir plugin) y FluentSMTP. Las solicitudes llegan a contacto@metalgenomic.cl y quedan copiadas en el menú «Solicitudes».
6. **Prueba real**: envía una solicitud desde el sitio publicado y confirma que llega.

## SEO (Rank Math o Yoast)

- **Título SEO**: `Metalgenomic · Biolixiviación genómica y BIM para minería del cobre`
- **Meta descripción**: `Diagnóstico de biolixiviación genómica y modelo BIM de planta para minería del cobre, en hasta 4 semanas. Primera reunión sin costo y NDA. Copiapó, Chile.`
- **Sitemap**: activa el sitemap de Rank Math (queda en `/sitemap_index.xml`) y envíalo a Google Search Console.
- **robots.txt**: usa el contenido de `robots.txt`.
- **Nombre**: usa siempre «Metalgenomic» (también en la solicitud a INAPI y en LinkedIn).

## Pendientes que dependen de ti (no se resuelven en el sitio)

- **Razón social**: hoy la sociedad registrada se llama Genomic Complexity SpA; cambiarla a Genomic Industries SpA (paso 0 de `PASOS.md`).
- **Equipo**: publicar nombres, cargos y LinkedIn de las personas o asesores reales. Hoy el sitio dice «red de especialistas» y que la propuesta indica quién participa.
- **Laboratorio de secuenciación**: firmar el acuerdo, documentar el protocolo de toma y envío de muestras y la cadena de custodia. El sitio ya dice que las muestras se secuencian «en un laboratorio especializado» y que la propiedad de los resultados queda por escrito.
- **Carpeta de proveedor minero**: certificado de vigencia de la sociedad, carpeta tributaria, seguro de responsabilidad civil, registro en la plataforma de proveedores del cliente y, para entrar a faena, inducción de seguridad y cobertura de accidentes del trabajo. Pregunta al área de abastecimiento de tu primer prospecto qué exige.
- **Matriz (genomicindustries.com)**: respaldar con literatura o quitar «Más recuperación, menos impacto ambiental».
- **LinkedIn**: página de empresa y un artículo técnico al mes.
