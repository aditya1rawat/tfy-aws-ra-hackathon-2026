'use client';
import { useState } from 'react';
import { mutate } from 'swr';
import { AuditPanel } from '@/components/AuditPanel';
import { BatchMonitorPanel } from '@/components/BatchMonitorPanel';
import { CostPanel } from '@/components/CostPanel';
import { ChaosControls } from '@/components/xray/ChaosControls';
import { EventLog } from '@/components/xray/EventLog';
import { NodeGraph } from '@/components/xray/NodeGraph';
import { ProofPanels } from '@/components/xray/ProofPanels';
import { ResilienceTimelinePanel } from '@/components/xray/ResilienceTimelinePanel';
import { useLive } from '@/hooks/useLive';
import {
	applyCascade,
	clearChaos,
	getResilience,
	getSystemState,
	getXrayRuns,
	setChaos,
	setLlmChaos,
	setLlmMode
} from '@/lib/api';

export default function XrayPage() {
	const system = useLive('/system/state', getSystemState);
	const xray = useLive('/xray/runs', () => getXrayRuns(20));
	const resilience = useLive('/xray/resilience', () => getResilience(), 1500);
	const [busy, setBusy] = useState(false);
	const runs = xray?.runs ?? [];
	const latest = runs[0] ?? null;

	const wrap = (fn: () => Promise<unknown>) => async () => {
		setBusy(true);
		try {
			await fn();
			await mutate('/system/state');
			await mutate('/xray/resilience');
		} finally {
			setBusy(false);
		}
	};

	return (
		<main className='min-h-screen bg-zinc-950 p-4 text-zinc-100'>
			<div className='mb-3 flex items-center justify-between'>
				<h1 className='font-bold'>🔬 Lifeline X-ray</h1>
				<ChaosControls
					state={system}
					busy={busy}
					onLlmMode={m =>
						wrap(() => (m === 'none' ? setLlmChaos(false) : setLlmMode(m)))()
					}
					onKillTool={wrap(() =>
						setChaos({
							server: 'chart',
							tool: 'get_patient_chart',
							mode: 'fail'
						})
					)}
					onCascade={wrap(() => applyCascade())}
					onClear={wrap(() => clearChaos())}
				/>
			</div>
			<div className='grid grid-cols-1 items-start gap-4 lg:grid-cols-4'>
				{/* Main column: batch on top, then live/event + proof/cost */}
				<div className='space-y-4 lg:col-span-3'>
					<BatchMonitorPanel tone='dark' />

					<div className='grid grid-cols-1 items-start gap-4 lg:grid-cols-3'>
						{/* Live run + event stream */}
						<section className='lg:col-span-2'>
							<div className='space-y-4 rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800'>
								<div>
									<h2 className='mb-2 text-[10px] uppercase tracking-wide text-zinc-500'>
										Live run · {latest?.patient_id ?? '—'}
									</h2>
									<NodeGraph run={latest} />
								</div>
								<div>
									<h2 className='mb-2 text-[10px] uppercase tracking-wide text-zinc-500'>
										Event stream
									</h2>
									<EventLog runs={runs} />
								</div>
							</div>
						</section>

						{/* Resilience timeline stacked on proof + cost / routing */}
						<section className='space-y-4 lg:col-span-1'>
							<ResilienceTimelinePanel events={resilience?.events ?? []} />
							<ProofPanels state={system} latest={latest} />
							<CostPanel tone='dark' />
						</section>
					</div>
				</div>

				{/* Right rail: audit trail — whole right side, alongside batch */}
				<aside className='lg:col-span-1 h-full'>
					<div className='lg:sticky lg:top-4 h-full'>
						<AuditPanel tone='dark' />
					</div>
				</aside>
			</div>
		</main>
	);
}
