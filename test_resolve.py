from pathlib import Path
def _resolve_pull_residue(pdb_path: Path, pull_residue: int) -> int:
    if pull_residue >= 0: return pull_residue
    last = -1
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM ", "HETATM")) and line[12:16].strip() == "CA":
            try:
                last = int(line[22:26])
            except ValueError:
                continue
    return last - 1

def correct_resolve(pdb_path: Path) -> int:
    ca_count = 0
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM ", "HETATM")) and line[12:16].strip() == "CA":
            ca_count += 1
    return ca_count - 1

pdb = Path("example/01.GettingStarted/pdb/1dfn.pdb")
print("Original:", _resolve_pull_residue(pdb, -1))
print("Correct:", correct_resolve(pdb))
