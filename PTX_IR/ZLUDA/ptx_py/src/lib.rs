use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Convert PTX source text to NVPTX LLVM IR text.
///
/// Args:
///     ptx_src: PTX assembly source as a string.
///     clock_rate_khz: GPU clock rate in kHz (used for %clock special register).
///                     Defaults to 1_000_000 (1 GHz) if 0 is passed.
///
/// Returns:
///     LLVM IR as a string (.ll text format).
///
/// Raises:
///     ValueError: on PTX parse error or translation error.
#[pyfunction]
#[pyo3(signature = (ptx_src, clock_rate_khz = 1_000_000))]
fn ptx_to_llvm_ir(ptx_src: &str, clock_rate_khz: u32) -> PyResult<String> {
    let ast = ptx_parser::parse_module_checked(ptx_src)
        .map_err(|e| PyValueError::new_err(format!("PTX parse error: {:?}", e)))?;

    let attrs = ptx::Attributes {
        clock_rate: if clock_rate_khz == 0 { 1_000_000 } else { clock_rate_khz },
    };

    let module = ptx::to_llvm_module(ast, attrs, |_| {})
        .map_err(|e| PyValueError::new_err(format!("PTX translate error: {:?}", e)))?;

    Ok(module.llvm_ir.print_module_to_string().to_string())
}

/// Python module: `import ptx_py`
#[pymodule]
fn ptx_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ptx_to_llvm_ir, m)?)?;
    Ok(())
}
