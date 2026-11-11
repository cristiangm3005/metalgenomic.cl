<?php
/**
 * Plugin Name:       Metalgenomic · Formulario de diagnóstico
 * Description:       Recibe las solicitudes del formulario de la landing y las envía a contacto@metalgenomic.cl. Guarda una copia en «Solicitudes» del panel.
 * Version:           1.0.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            Genomic Industries SpA
 * License:           GPL-2.0-or-later
 * Text Domain:       metalgenomic-formulario
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Correo que recibe las solicitudes. */
const MG_FORM_TO = 'contacto@metalgenomic.cl';
/** Máximo de envíos por IP en 10 minutos (protección contra abuso). */
const MG_FORM_LIMIT = 5;

/**
 * Copia de cada solicitud en el panel (menú «Solicitudes»), por si un correo no llega.
 * Solo la ven los administradores; no se publica en el sitio.
 */
add_action(
	'init',
	function () {
		register_post_type(
			'mg_solicitud',
			array(
				'labels'          => array(
					'name'          => 'Solicitudes',
					'singular_name' => 'Solicitud',
					'menu_name'     => 'Solicitudes',
					'all_items'     => 'Todas las solicitudes',
					'edit_item'     => 'Ver solicitud',
					'not_found'     => 'Aún no hay solicitudes.',
				),
				'public'          => false,
				'show_ui'         => true,
				'show_in_menu'    => true,
				'show_in_rest'    => false,
				'menu_icon'       => 'dashicons-email-alt',
				'supports'        => array( 'title', 'editor' ),
				'capability_type' => 'post',
				'capabilities'    => array( 'create_posts' => 'do_not_allow' ),
				'map_meta_cap'    => true,
			)
		);
	}
);

add_action(
	'rest_api_init',
	function () {
		register_rest_route(
			'metalgenomic/v1',
			'/contacto',
			array(
				'methods'             => 'POST',
				'callback'            => 'mg_form_handle',
				'permission_callback' => '__return_true',
			)
		);
	}
);

/** Lee un campo como texto limpio y acotado. */
function mg_form_field( WP_REST_Request $req, $key, $max = 300 ) {
	$v = $req->get_param( $key );
	if ( is_array( $v ) ) {
		$v = implode( ', ', $v );
	}
	$v = sanitize_textarea_field( (string) $v );
	return function_exists( 'mb_substr' ) ? mb_substr( $v, 0, $max ) : substr( $v, 0, $max );
}

function mg_form_error( $msg, $status ) {
	return new WP_REST_Response( array( 'ok' => false, 'error' => $msg ), $status );
}

function mg_form_handle( WP_REST_Request $req ) {
	// Campo trampa: las personas no lo ven; si viene lleno es un robot. Se responde «ok» sin enviar nada.
	if ( '' !== trim( (string) $req->get_param( 'web' ) ) ) {
		return new WP_REST_Response( array( 'ok' => true ), 200 );
	}

	$ip  = isset( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
	$key = 'mg_form_' . md5( $ip );
	$n   = (int) get_transient( $key );
	if ( $n >= MG_FORM_LIMIT ) {
		return mg_form_error( 'Demasiadas solicitudes seguidas. Intenta en unos minutos.', 429 );
	}

	$f = array(
		'nombre'   => sanitize_text_field( mg_form_field( $req, 'nombre', 120 ) ),
		'cargo'    => sanitize_text_field( mg_form_field( $req, 'cargo', 120 ) ),
		'empresa'  => sanitize_text_field( mg_form_field( $req, 'empresa', 160 ) ),
		'telefono' => sanitize_text_field( mg_form_field( $req, 'telefono', 40 ) ),
		'correo'   => sanitize_email( mg_form_field( $req, 'correo', 160 ) ),
		'interes'  => sanitize_text_field( mg_form_field( $req, 'interes', 400 ) ),
		'etapa'    => sanitize_text_field( mg_form_field( $req, 'etapa', 120 ) ),
		'mensaje'  => mg_form_field( $req, 'mensaje', 2000 ),
	);

	if ( '' === $f['nombre'] || '' === $f['empresa'] || ! is_email( $f['correo'] ) ) {
		return mg_form_error( 'Faltan el nombre, la empresa o un correo válido.', 400 );
	}
	if ( 'si' !== $req->get_param( 'acepta_privacidad' ) ) {
		return mg_form_error( 'Falta aceptar la política de privacidad.', 400 );
	}

	set_transient( $key, $n + 1, 10 * MINUTE_IN_SECONDS );

	$subject = 'Diagnóstico operativo · ' . $f['empresa'];
	$lines   = array(
		'Solicitud de diagnóstico operativo (formulario de metalgenomic.cl)',
		'',
		'Interés: ' . ( $f['interes'] ? $f['interes'] : '—' ),
		'Etapa: ' . ( $f['etapa'] ? $f['etapa'] : '—' ),
		'Problema: ' . ( $f['mensaje'] ? $f['mensaje'] : '—' ),
		'',
		'Nombre: ' . $f['nombre'],
		'Cargo: ' . ( $f['cargo'] ? $f['cargo'] : '—' ),
		'Empresa / faena: ' . $f['empresa'],
		'Teléfono: ' . ( $f['telefono'] ? $f['telefono'] : '—' ),
		'Correo: ' . $f['correo'],
		'',
		'Aceptó la política de privacidad: sí',
		'Fecha: ' . wp_date( 'd-m-Y H:i' ),
	);
	$body = implode( "\n", $lines );

	// «Responder» en tu correo contesta directo a quien escribió.
	$reply   = str_replace( array( '"', '<', '>', "\r", "\n" ), '', $f['nombre'] );
	$headers = array(
		'Content-Type: text/plain; charset=UTF-8',
		'Reply-To: "' . $reply . '" <' . $f['correo'] . '>',
	);

	$sent = wp_mail( MG_FORM_TO, $subject, $body, $headers );

	wp_insert_post(
		array(
			'post_type'    => 'mg_solicitud',
			'post_status'  => 'private',
			'post_title'   => $subject . ' · ' . $f['nombre'],
			'post_content' => $body . "\n\nCorreo enviado a " . MG_FORM_TO . ': ' . ( $sent ? 'sí' : 'NO (revisa FluentSMTP)' ),
		)
	);

	if ( ! $sent ) {
		// El formulario de la landing ofrece entonces enviar por el programa de correo del visitante.
		return mg_form_error( 'No se pudo enviar el correo.', 500 );
	}
	return new WP_REST_Response( array( 'ok' => true ), 200 );
}
