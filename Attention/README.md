```
cd /xplorer/shijy/PTX_To_SASS
mkdir -p Attention/cubins

for f in Attention/*.ptx; do
name=$(basename "$f" .ptx)
ptxas -arch=sm_110f -O0 -lineinfo -o "Attention/cubins/${name}_O0.cubin" "$f"
ptxas -arch=sm_110f -O3 -lineinfo -o "Attention/cubins/${name}_O3.cubin" "$f"
done
```


```
set -u
mkdir -p Attention/cubins Attention/sass
status=0
```
