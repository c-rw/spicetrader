import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url, fetch }) => {
	const base = process.env.API_BASE_URL ?? 'http://localhost:8000';
	const apiKey = process.env.DASHBOARD_API_KEY ?? '';
	const target = new URL('/api/overview', base);
	target.search = url.search;

	const headers: Record<string, string> = {
		accept: 'application/json'
	};
	if (apiKey) {
		headers['Authorization'] = `Bearer ${apiKey}`;
	}

	const res = await fetch(target.toString(), { headers });

	const bodyText = await res.text();
	if (!res.ok) {
		return new Response(bodyText, {
			status: res.status,
			headers: {
				'content-type': res.headers.get('content-type') ?? 'text/plain'
			}
		});
	}

	try {
		return json(JSON.parse(bodyText));
	} catch {
		return new Response(bodyText, {
			status: 200,
			headers: {
				'content-type': 'application/json'
			}
		});
	}
};
