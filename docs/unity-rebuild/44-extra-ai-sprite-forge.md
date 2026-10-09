# 44 - Extra: Pixel Sprite Forge, the local AI sprite pipeline (and why this is a fully AI-made game)

## A fully AI-made game
Realm Reforged is a **fully AI-made game**. A human directed it: the ideas, the feedback, play-testing and every "make it bigger / tougher / goofier". AI made all of the rest:
- the code: client, server, world generation, AI, netcode
- the design numbers and the docs (this folder)
- the 88 test scripts
- the hand-painted and procedural sprites
- the procedurally synthesised music and sound

Claude Code wrote and painted everything in this repository. This doc covers an **optional extra** for anyone who wants to keep making the game the same way: a local, free, GPU-powered pipeline that turns a text description into a clean pixel-art sprite.

The art rules stay the same:
- **Players and NPCs stay chunky pixel art**, a little bigger than ROTMG (doc 43 rule).
- Detailed art is for monsters and bosses.
- Everything that ships must be original. AI-generated sprites come from text prompts, never from tracing someone else's art. Reference pictures in `references/` are for poses and ideas only.

## What it is
`pixel-sprite-forge/pixel-sprite-forge/` is **local-only and git-ignored**. That's about 10 GB of tools and models; none of it ships with the game.

| Part | What it does |
|---|---|
| `ComfyUI_windows_portable/` | ComfyUI with its own Python 3.13 + PyTorch built for CUDA 13; it runs the model on the NVIDIA GPU |
| `.../models/checkpoints/sd_xl_base_1.0.safetensors` | the base image model, SDXL (6.9 GB) |
| `.../models/vae/sdxl_vae.safetensors` | the fp16-fix VAE, so decoding in fp16 doesn't produce black images |
| `.../models/loras/pixel-art-xl.safetensors` | the Pixel Art XL LoRA, which gives the pixel-art style |
| `.../models/loras/lcm-lora-sdxl.safetensors` | the LCM-LoRA, which lets the fast route use 8 steps instead of 30 |
| `prompts/characters.json` | a shared style and negative prompt, plus one `desc` per sprite (`grid`, `height`, `anchor`, `colors` per sprite) |
| `workflows/sdxl_pixel_api.json` | the **quality** route: 30 steps, CFG 6.5, dpmpp_2m karras, 1024² |
| `workflows/sdxl_pixel_fast_api.json` | the **fast** route: pixel LoRA (1.2) → LCM-LoRA, 8 steps, CFG 2.0, `lcm` / `sgm_uniform` |
| `scripts/generate.py` | sends the prompts to ComfyUI over HTTP (`--only`, `--variants`, `--batch`, `--seed`) |
| `scripts/postprocess.py` | removes the white background, snaps to the real pixel grid, reduces the palette, adds a 1 px outline, exports 48 px + @2x, and builds a contact sheet |

## Install (SDXL route, Windows + NVIDIA)
1. **Driver only.** You need an NVIDIA driver of 580 or newer (this machine has 581.95). Don't install the CUDA Toolkit or cuDNN; the portable build brings its own.
2. Run `1_install_comfyui.bat`. It downloads and extracts ComfyUI portable (about 2 GB).
3. Run `2_download_sdxl_models.bat`. It fetches the four model files (about 7.9 GB) and can be resumed.
4. **Behind a proxy that resets long downloads**, which this office network does: use `bash _dl_comfy.sh` and `bash _dl_models.sh` instead. They resume after every reset. Then move `_models_staging/*` into `ComfyUI_windows_portable/ComfyUI/models/`. Check the SHA-256 of each file against the `X-Linked-ETag` header Hugging Face sends.
   - On this machine `cmd` would not run the `.bat` files from the agent shell; they work fine from Explorer or a normal terminal.

## Making sprites
1. Run `3_start_comfyui.bat` and leave the window open; the UI is at http://127.0.0.1:8188.
2. Generate with either route:
   - fast: `4_generate_sprites.bat fast 2`, which makes 2 requests of 4 images per sprite
   - quality: `4_generate_sprites.bat sdxl 3`
   - or just some sprites: `python_embeded\python.exe scripts\generate.py --workflow workflows\sdxl_pixel_fast_api.json --map workflows\sdxl_pixel_api.map.json --only class_wizard --variants 1 --batch 4`
3. Run `5_postprocess.bat`. Clean sprites land in `output/sprites/`, and `_contact_sheet.png` opens so you can pick the best variant.
4. Touch up in Aseprite or Pixelorama if needed, then copy into `assets/sprites/v0.2/...` using the game's naming:
   - `enemy_<kind>.png` plus `_anim` / `_attack` strips, or
   - `player_<cls>.png`, then run `python tools/pixel_player_strips.py <cls>` to rebuild the idle / walk / shoot strips.
5. Re-run `python tests/run_all_checks.py` (`check_sprite_quality` checks the sizes and alpha), take screenshots, and update the docs as usual.

## Full GPU use: what has to be true
- **The GPU is actually used.** When ComfyUI starts, its log must show `Device: cuda:0 NVIDIA GeForce RTX 5050 ...`. While it runs, `http://127.0.0.1:8188/system_stats` lists the CUDA device and its VRAM. If you see `cpu`, the driver is too old or the wrong ComfyUI build was installed (it must be the `_nvidia` portable).
- **The right CUDA for the GPU.** The RTX 50 series (Blackwell, sm_120) needs PyTorch built for **CUDA 12.8 or newer**. The portable build's torch with CUDA 13 qualifies; an older torch would fail with "no kernel image".
  - Measured here: ComfyUI 0.39.0 with PyTorch **2.14.0+cu130** (CUDA 13.0); the supported architectures include **sm_120**, and `torch.cuda.is_available()` is True
- **Laptops with two GPUs (Intel + NVIDIA):** CUDA always runs on the NVIDIA card. The Windows "Graphics preference" setting only affects which GPU *displays* an app, so it doesn't need changing.
- **Power:** plug the laptop in (on battery the GPU clocks down hard) and set Windows power mode to **Best performance**. In the vendor tool (Armoury Crate, Vantage, etc.), pick Performance / Turbo.
- **VRAM:** SDXL in fp16 with the LoRAs needs about 6–7 GB of the 8 GB. Close the game, browsers with hardware acceleration and video players while generating. With `--lowvram` it still works, but slower.
- **Keep ComfyUI open.** The first image loads the model (cold start **48.5 s** for the first image, which includes loading the model from disk); after that it stays in VRAM and every request starts immediately.

## Making it as fast as possible
Measured on the RTX 5050 Laptop (8 GB), 1024², one sprite description:

| Setup | Time per image | Usable images | Time per *usable* sprite |
|---|---|---|---|
| First image after starting (cold) | 48.5 s | - | - |
| Quality route (30 steps, CFG 6.5), `--fast`, warm | **22.6 s** | almost all | ~23 s |
| Fast route (LCM 8 steps), batch 1 | **7.5 s** | - | - |
| Fast route, batch 4, untuned (CFG 1.5, pixel LoRA 1.0) | 6.4 s | 2 of 10 | ~32 s (worse!) |
| **Fast route, batch 4, tuned (CFG 2.0, pixel LoRA 1.2)**, the shipped setting | **6.6 s** | **5 of 8** | **~10.5 s** |

What the tuning showed (`screenshots/2026-10-09/sprite_forge/02_fast_route_tuning.png`):
- Too little guidance (CFG 1.5) makes LCM draw flat, washed-out silhouettes on a grey background. Postprocess can't cut out a grey background, so those images are wasted.
- CFG 2.0 plus a stronger pixel LoRA (1.2) fixes most of them.
- CFG 2.5 with 10 steps and LCM at 0.8 was slower (8 s) and no better.

So use the fast route to explore (lots of cheap variants, pick from the contact sheet) and the quality route for a final pass on one description.

**Already applied:**
- **`--fast`**, the default in `3_start_comfyui.bat`. It turns on fp16 accumulation and fp8 matrix maths where the GPU supports them, which Blackwell does. `3_start_comfyui.bat safe` turns it off if a driver ever rejects it.
- **`--preview-method none`.** Live previews cost time on every step.
- **The LCM-LoRA fast route.** 8 steps instead of 30: 3.4× faster per image and about 2× faster per *usable* sprite (tuned to CFG 2.0, pixel LoRA 1.2). The style stays because the pixel LoRA runs first; postprocess snaps everything to the grid anyway.
- **Batching (`--batch 4`).** Four images in one GPU pass share the overhead. That's a small gain here (7.5 → 6.6 s); the bigger win is that a single command gives you four variants to choose from.
- **A warm model.** ComfyUI's default smart memory keeps SDXL loaded between requests.

**Bigger wins (documented, not installed):**
- **TensorRT** (the `ComfyUI_TensorRT` custom node): about 1.5–2× more on SDXL. You build an engine once per resolution and batch size, which takes minutes and a few GB of disk. Worth it if you generate hundreds of sprites.
- **SageAttention** (needs `triton-windows` + `sageattention` installed into `python_embeded`, then `--use-sage-attention`): about 10–30% faster attention. Fiddlier to install on Windows.
- **Lower resolution** (768² instead of 1024²): about 1.8× fewer pixels. Fine for 48-px sprites because postprocess downsamples anyway, but Pixel Art XL was trained at 1024, so check the contact sheet.
- **fp8 UNet weights** (`--fp8_e4m3fn-unet`): frees about 2.5 GB of VRAM, which helps if something else is using the GPU. Slightly lower quality.
- **Fewer variants plus a fixed seed** (`--seed N`) once you like a look: the cheapest speed-up of all.
- **IPAdapter** (`ComfyUI_IPAdapter_plus`) with one approved sprite as a style reference: fewer rejected variants, so fewer images to generate.
- **Don't** install the CUDA Toolkit, cuDNN or a system-wide PyTorch. They don't make the portable build faster, and they can conflict with it.

## Verification done
- **GPU check:** ComfyUI started with `--fast`; `/system_stats` reported `cuda:0 NVIDIA GeForce RTX 5050 Laptop GPU : native`, 8 GB VRAM, `NORMAL_VRAM`, PyTorch attention, DynamicVRAM on.
- **Generation:** both routes generated `class_wizard` / `class_archer`, and postprocess made the contact sheet. Screenshot: `screenshots/2026-10-09/sprite_forge/`.
- **Git:** `git status` doesn't show `pixel-sprite-forge/`.
