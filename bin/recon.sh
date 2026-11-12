#!/usr/bin/env bash
# usage: bin/recon.sh <target> passive|active
# passive: no traffic to the target. active: only hosts in work/scope_hosts.txt, with research header, <=5 req/s.
set -euo pipefail
export PATH="$HOME/go/bin:$PATH"
cd "$(dirname "$0")/../${1:?target}"
W=work; J=$W/target.json; MODE=${2:?passive|active}
DOMAINS=$(jq -r '.root_domains[]' $J)
HN=$(jq -r '.research_header[0]' $J); HV=$(jq -r '.research_header[1]' $J)
case $MODE in
passive)
  P=$W/recon/passive; mkdir -p $P
  for d in $DOMAINS; do
    subfinder -d $d -silent >> $P/subs_raw.txt || true
    curl -s "https://crt.sh/?q=%25.$d&output=json" | jq -r '.[].name_value' 2>/dev/null | tr 'A-Z' 'a-z' | sed 's/^\*\.//' >> $P/subs_raw.txt || true
    gau --subs $d 2>/dev/null | head -50000 >> $P/urls_archive.txt || true
  done
  sort -u $P/subs_raw.txt > $P/subs.txt
  dnsx -silent -a -cname -resp -l $P/subs.txt > $P/dns.txt || true
  wc -l $P/*.txt
  echo "Next: spawn recon-digester on $P/ -> $W/recon/host_classification.md";;
active)
  A=$W/recon/active; JS=$W/recon/js; mkdir -p $A $JS
  grep -v '^\s*#' $W/scope_hosts.txt | grep -v '^\s*$' > $A/hosts.txt
  [ -s $A/hosts.txt ] || { echo "scope_hosts.txt is empty"; exit 1; }
  pdhttpx -l $A/hosts.txt -H "$HN: $HV" -rl 5 -silent -status-code -title -tech-detect -json > $A/httpx.jsonl
  katana -list $A/hosts.txt -H "$HN: $HV" -rl 5 -d 3 -jc -silent -o $A/crawl.txt
  grep -E '\.js(\?|$)' $A/crawl.txt | sort -u > $A/js_urls.txt
  # fetch JS only from allowlisted hosts, rate limited, with header
  while read -r u; do
    h=$(echo "$u" | awk -F/ '{print $3}')
    grep -qx "$h" $A/hosts.txt || continue
    curl -s -H "$HN: $HV" "$u" -o "$JS/$(echo "$u" | sha1sum | cut -c1-12).js"; sleep 0.2
  done < $A/js_urls.txt
  wc -l $A/*.txt; ls $JS | wc -l
  echo "Next: spawn js-analyzer on $JS/ and recon-digester on $A/";;
esac
