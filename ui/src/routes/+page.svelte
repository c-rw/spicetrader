<script lang="ts">
	import { onMount } from 'svelte';

	type Overview = {
		meta: {
			generated_at: string;
			range: { start: string; end: string };
			filters: { dry_run: string; symbols: string[] };
		};
		kpis: any;
		timeseries: any;
		tables: any;
		breakdowns: any;
	};

	let data: Overview | null = null;
	let error: string | null = null;
	let loading = true;

	async function loadOverview() {
		loading = true;
		error = null;
		try {
			const res = await fetch('/api/overview');
			if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
			data = (await res.json()) as Overview;
		} catch (e: any) {
			error = e?.message ?? 'Failed to load dashboard data';
		} finally {
			loading = false;
		}
	}

	onMount(loadOverview);
</script>

<main>
	<h1>SpiceTrader Dashboard</h1>

	{#if loading}
		<p>Loading…</p>
	{:else if error}
		<p>Error: {error}</p>
	{:else if data}
		<p>
			Generated: {data.meta.generated_at}
			<br />
			Range: {data.meta.range.start} → {data.meta.range.end}
			<br />
			Dry run: {data.meta.filters.dry_run}
		</p>

		<section>
			<h2>KPIs</h2>
			<ul>
				<li>Closed positions: {data.kpis.positions_closed.total}</li>
				<li>Win rate: {data.kpis.positions_closed.win_rate.toFixed(1)}%</li>
				<li>Net PnL: {data.kpis.pnl.net.toFixed(2)}</li>
				<li>Fees: {data.kpis.pnl.fees.toFixed(2)}</li>
				<li>Open positions: {data.kpis.exposure.open_positions_count}</li>
			</ul>
		</section>

		<section>
			<h2>Open Positions</h2>
			{#if data.tables.open_positions.length === 0}
				<p>No open positions.</p>
			{:else}
				<table>
					<thead>
						<tr>
							<th>Symbol</th>
							<th>Strategy</th>
							<th>Type</th>
							<th>Entry</th>
							<th>Volume</th>
							<th>Notional</th>
						</tr>
					</thead>
					<tbody>
						{#each data.tables.open_positions as p}
							<tr>
								<td>{p.symbol}</td>
								<td>{p.strategy}</td>
								<td>{p.position_type}</td>
								<td>{p.entry_price}</td>
								<td>{p.entry_volume}</td>
								<td>{p.notional_usd.toFixed(2)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</section>

		<section>
			<h2>Recent Trades</h2>
			{#if data.tables.recent_trades.length === 0}
				<p>No trades in range.</p>
			{:else}
				<table>
					<thead>
						<tr>
							<th>Time</th>
							<th>Symbol</th>
							<th>Side</th>
							<th>Price</th>
							<th>Volume</th>
							<th>Fee</th>
						</tr>
					</thead>
					<tbody>
						{#each data.tables.recent_trades as t}
							<tr>
								<td>{t.timestamp}</td>
								<td>{t.symbol}</td>
								<td>{t.side}</td>
								<td>{t.price}</td>
								<td>{t.volume}</td>
								<td>{t.fee} {t.fee_currency}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</section>
	{/if}
</main>
