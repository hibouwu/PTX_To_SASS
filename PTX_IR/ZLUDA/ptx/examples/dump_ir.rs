// Convert a PTX file to LLVM IR text and print to stdout.
use std::{env, fs};

fn main() {
    let path = env::args().nth(1).expect("usage: dump_ir <file.ptx>");
    let src = fs::read_to_string(&path).expect("failed to read file");

    let ast = ptx_parser::parse_module_checked(&src)
        .unwrap_or_else(|e| panic!("parse error: {:?}", e));

    let attrs = ptx::Attributes { clock_rate: 1_000_000 };
    let module = ptx::to_llvm_module(ast, attrs, |pass| eprintln!("  pass: {}", pass))
        .unwrap_or_else(|e| panic!("translate error: {:?}", e));

    let ir = module.llvm_ir.print_module_to_string();
    print!("{}", ir);
}
