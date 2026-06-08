'use client';
import { useState } from 'react';
import { mutate } from 'swr';
import { AuditPanel } from '@/components/AuditPanel';
import { BatchMonitorPanel } from '@/components/BatchMonitorPanel';
import { CostPanel } from '@/components/CostPanel';
import { ChaosControls } from '@/components/xray/ChaosControls';
import { DemoBar } from '@/components/xray/DemoBar';
import { EventLog } from '@/components/xray/EventLog';
import { GatewayTelemetryPanel } from '@/components/xray/GatewayTelemetryPanel';
import { LiveNodeList } from '@/components/patient/LiveNodeList';
import { NodeGraph } from '@/components/xray/NodeGraph';
import { ProofPanels } from '@/components/xray/ProofPanels';
import { ResilienceTimelinePanel } from '@/components/xray/ResilienceTimelinePanel';
import { useLive } from '@/hooks/useLive';
import { useNodeStream } from '@/hooks/useNodeStream';
import {
	applyCascade,
	clearChaos,
	getResilience,
	getSystemState,
	getTelemetry,
	getXrayRuns,
	resetDemo,
	seedHero,
	setChaos,
	setDoseHallucinate,
	setGatewayFailover,
	setLlmChaos,
	setLlmMode
} from '@/lib/api';
import { notify, notifyError } from '@/lib/toast';

export default function XrayPage() {
	const system = useLive('/system/state', getSystemState);
	const xray = useLive('/xray/runs', () => getXrayRuns(20));
	const resilience = useLive('/xray/resilience', () => getResilience(), 1500);
	const telemetry = useLive('/xray/telemetry', () => getTelemetry(20), 2000);
	const [busy, setBusy] = useState(false);
	const stream = useNodeStream();
	const runs = xray?.runs ?? [];
	const latest = runs[0] ?? null;

	const wrap = (fn: () => Promise<unknown>, label?: string) => async () => {
		setBusy(true);
		try {
			await fn();
			await mutate('/system/state');
			await mutate('/xray/resilience');
			if (label) notify(label);
		} catch {
			if (label) notifyError(`${label} failed`);
		} finally {
			setBusy(false);
		}
	};

	const onRun = async () => {
		try {
			await stream.start({ patient_id: 'p_001', med_id: 'm_aspirin', request_type: 'refill' });
			notify('Hero request complete');
		} catch {
			notifyError('Live run failed');
		} finally {
			await mutate('/xray/runs');
			await mutate('/xray/resilience');
		}
	};
	// Dose-hold hero: arm the dose-hallucination lever, then stream a lisinopril
	// refill. The drafter overstates the dose (80 mg > 40 mg ceiling), the gateway
	// dosage guardrail returns a 400, and the run escalates with the dosage-block
	// beat — giving that gateway control a one-click UI trigger.
	const onRunDose = async () => {
		setBusy(true);
		try {
			await setDoseHallucinate(true);
			await mutate('/system/state');
			await stream.start({ patient_id: 'p_001', med_id: 'm_lisinopril', request_type: 'refill' });
			notify('Dose-hold request complete');
		} catch {
			notifyError('Dose-hold run failed');
		} finally {
			setBusy(false);
			await mutate('/xray/runs');
			await mutate('/xray/resilience');
		}
	};
	const onSeed = wrap(() => seedHero(), 'Hero seeded');
	const onReset = wrap(() => resetDemo(), 'Demo reset');

	// Reset the ephemeral live-run frames and refetch the persisted runs/timeline
	// so a chaos clear or batch wipe empties the Live-run + Event-stream panels
	// without a page refresh.
	const clearRunPanels = () => {
		stream.reset();
		mutate('/xray/runs');
		mutate('/xray/resilience');
	};
	const onClearChaos = wrap(async () => {
		await clearChaos();
		clearRunPanels();
	}, 'Chaos cleared');

	return (
		<main className='min-h-screen bg-zinc-950 p-4 text-zinc-100'>
			<div className='mb-3 flex items-center justify-between gap-3'>
				<h1 className='font-bold'>🔬 Lifeline X-ray</h1>
				<div className='flex flex-wrap items-center gap-2'>
					<DemoBar busy={busy || stream.running} onRun={onRun} onRunDose={onRunDose} onSeed={onSeed} onReset={onReset} />
					<div className='mx-1 h-6 w-px bg-zinc-800' aria-hidden />
					<ChaosControls
						state={system}
						busy={busy}
						onLlmMode={m =>
							wrap(
								() => (m === 'none' ? setLlmChaos(false) : setLlmMode(m)),
								`LLM: ${m}`
							)()
						}
						onKillTool={wrap(
							() =>
								setChaos({
									server: 'chart',
									tool: 'get_patient_chart',
									mode: 'fail'
								}),
							'Chart tool killed'
						)}
						onKillInteraction={wrap(
							() =>
								setChaos({
									server: 'interactions',
									tool: 'check_interaction',
									mode: 'fail'
								}),
							'Interaction check killed'
						)}
						onGatewayFailover={on =>
							wrap(
								() => setGatewayFailover(on),
								on ? 'Gateway failover armed' : 'Gateway failover disarmed'
							)()
						}
						onDoseHallucinate={on =>
							wrap(
								() => setDoseHallucinate(on),
								on ? 'Dose hallucination armed' : 'Dose hallucination disarmed'
							)()
						}
						onCascade={wrap(() => applyCascade(), 'Cascade applied')}
						onClear={onClearChaos}
					/>
				</div>
			</div>
			<div className='grid grid-cols-1 items-start gap-4 lg:grid-cols-4'>
				{/* Main column: batch on top, then live/event + proof/cost */}
				<div className='space-y-4 lg:col-span-3'>
					<BatchMonitorPanel tone='dark' onCleared={clearRunPanels} />

					<div className='grid grid-cols-1 items-start gap-4 lg:grid-cols-3'>
						{/* Live run + event stream */}
						<section className='lg:col-span-2'>
							<div className='space-y-4 rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800'>
								<div>
									<h2 className='mb-2 text-[10px] uppercase tracking-wide text-zinc-500'>
										Live run · {latest?.patient_id ?? '—'}
									</h2>
									{stream.running || stream.events.length > 0 ? (
											<LiveNodeList events={stream.events} />
										) : (
											<NodeGraph run={latest} />
										)}
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
							<GatewayTelemetryPanel calls={telemetry?.calls ?? []} />
							<ProofPanels state={system} latest={latest} />
							<CostPanel tone='dark' />
						</section>
					</div>
				</div>

				{/* Right rail: audit trail — whole right side, alongside batch */}
				<aside className='lg:col-span-1'>
					<div className='lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)]'>
						<AuditPanel tone='dark' />
					</div>
				</aside>
			</div>
		</main>
	);
}
