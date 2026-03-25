{
  writeShellApplication,
  writeShellScript,
  certbot,
  namecheap-hook,
}:
let
  authHook = writeShellScript "auth-hook" ''
    ${namecheap-hook}/bin/namecheap-hook auth && sleep 30
  '';

  cleanupHook = writeShellScript "cleanup-hook" ''
    ${namecheap-hook}/bin/namecheap-hook cleanup
  '';
in
writeShellApplication {
  name = "namecheap-certbot";

  runtimeInputs = [
    certbot
    namecheap-hook
  ];

  text = ''
    while IFS='=' read -r key val; do
      case "$key" in
        NAMECHEAP_AUTH_TOKEN) export NAMECHEAP_AUTH_TOKEN="$val" ;;
        NAMECHEAP_CSRF_TOKEN) export NAMECHEAP_CSRF_TOKEN="$val" ;;
      esac
    done <<< "$(namecheap-hook login | grep -E '^[A-Z_]+=.*')"

    certbot "$1" \
      --manual \
      --preferred-challenges=dns \
      --manual-auth-hook ${authHook} \
      --manual-cleanup-hook ${cleanupHook} \
      "''${@:2}"
  '';
}
