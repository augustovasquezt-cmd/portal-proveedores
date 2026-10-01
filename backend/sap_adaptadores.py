"""Puntos de extensión por producto SAP. Sin transporte configurado por defecto."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PerfilSAP:
    id: str
    nombre: str
    interfaz: str
    requisitos: tuple[str,...]

PERFILES={
 'ecc':PerfilSAP('ecc','SAP ECC','BAPI/RFC mediante middleware',('version_ecc','middleware','sociedad','proveedor_sap','codigos_impuesto','accion_documento')),
 's4hana':PerfilSAP('s4hana','SAP S/4HANA','API de factura de proveedor habilitada en el sistema',('version_s4','endpoint','autenticacion','sociedad','proveedor_sap','codigos_impuesto','accion_documento')),
 's4hana_grow':PerfilSAP('s4hana_grow','SAP S/4HANA Cloud Public Edition (GROW)','API liberada y communication arrangement',('tenant','communication_arrangement','endpoint','autenticacion','sociedad','proveedor_sap','codigos_impuesto','accion_documento')),
}
class AdaptadorSAP:
    """El transporte debe confirmar documento SAP antes de marcar un envío exitoso."""
    def __init__(self,perfil): self.perfil=PERFILES[perfil]
    def enviar(self,contenido,clave_idempotencia):
        raise RuntimeError('Transporte SAP no configurado; no se ha enviado la factura.')

def adaptador(perfil):return AdaptadorSAP(perfil)
