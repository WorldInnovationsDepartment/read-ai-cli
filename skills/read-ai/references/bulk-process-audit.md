# Bulk Read AI Process Audit Pattern

Use when the user asks to read all meetings over a period and infer company/process patterns.

## Workflow

1. List all meetings with a high enough limit, not the default page:
   ```bash
   mkdir -p /tmp/readai_process_audit
   readai meetings --days 60 --limit 300 --json > /tmp/readai_process_audit/meetings_raw.json
   ```
2. Strip any CLI log lines before JSON and persist normalized meeting metadata:
   ```python
   import json
   s=open('/tmp/readai_process_audit/meetings_raw.json').read()
   arr=json.loads(s[s.find('['):])
   open('/tmp/readai_process_audit/meetings.json','w').write(json.dumps(arr,ensure_ascii=False,indent=2))
   print(len(arr))
   ```
3. Fetch details for each meeting with expanded fields. Use a single sequential process to avoid token-refresh races:
   ```python
   import json, subprocess, time, os
   meetings=json.load(open('/tmp/readai_process_audit/meetings.json'))
   outdir='/tmp/readai_process_audit/details'; os.makedirs(outdir, exist_ok=True)
   fields='summary chapter_summaries action_items key_questions topics metrics transcript'
   for i,m in enumerate(meetings,1):
       mid=m['id']; fp=f'{outdir}/{mid}.json'
       if os.path.exists(fp) and os.path.getsize(fp)>100: continue
       r=subprocess.run(['readai','get',mid,'--expand',*fields.split(),'--json'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
       s=r.stdout; jstart=s.find('{')
       if r.returncode or jstart < 0:
           open(fp+'.err','w').write(s); continue
       open(fp,'w').write(json.dumps(json.loads(s[jstart:]), ensure_ascii=False))
       time.sleep(0.35)
   ```
4. Build a digest for analysis: title/date/participants/summary/topics/actions/questions. Then analyze by recurring meeting titles, folders, participants, and repeated action patterns.
5. For large corp/process audits, delegate separate analysis streams (operations/people, delivery/accounts, AI/research/sales), then synthesize a concise executive report.
6. If delivering over Telegram, do not send raw `.md`; convert to DOCX/PDF first.

## Pitfalls

- `readai meetings` can print `✓ Token refreshed` before JSON; strip before parsing.
- The API page size is small; use CLI auto-pagination with `--limit` high enough.
- Expanding transcript is slow; use sequential calls and resume from existing files.
- Transcript turns are reverse chronological; rely mostly on summary/topics/actions unless exact quotes are needed.
- Bulk fetching is useful but expensive in time; keep raw details in `/tmp/.../details` for resuming within the session.
