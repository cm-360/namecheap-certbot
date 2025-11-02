{
  description = "Certbot DNS-01 challenge hook for Namecheap";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" ];

      forAllSystems =
        function:
        nixpkgs.lib.genAttrs supportedSystems (
          system:
          function (
            import nixpkgs {
              inherit system;
              overlays = [ self.overlays.default ];
            }
          )
        );
    in
    {
      overlays.default = final: prev: {
        namecheap-certbot = final.callPackage ./namecheap-certbot.nix { };
        namecheap-hook = final.callPackage ./namecheap-hook.nix { };
      };

      packages = forAllSystems (pkgs: rec {
        inherit (pkgs)
          namecheap-certbot
          namecheap-hook
          ;
        default = namecheap-certbot;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            namecheap-certbot
            namecheap-hook
          ];
        };
      });
    };
}
